import ast
import opcode
import threading
import traceback
from collections import defaultdict
from datetime import datetime
from textwrap import dedent

import executing
import six

from snoop.utils import ensure_tuple, short_filename, with_needed_parentheses, my_cheap_repr, \
    NO_ASTTOKENS, optional_numeric_label, try_statement, FormattedValue


class StatementsDict(dict):
    def __init__(self, source):
        super(StatementsDict, self).__init__()
        self.source = source

    def __missing__(self, key):
        statements = self.source.statements_at_line(key)
        if len(statements) == 1:
            result = list(statements)[0]
        else:
            result = None
        self[key] = result
        return result


class Source(executing.Source):
    def __init__(self, *args, **kwargs):
        super(Source, self).__init__(*args, **kwargs)
        if self.tree:
            self.lines = self.text.splitlines()
        else:
            self.lines = defaultdict(lambda: u'SOURCE IS UNAVAILABLE')
        self.statements = StatementsDict(self)
        self.nodes = []
        if self.tree:
            self.tree._depth = 0
            for node in ast.walk(self.tree):
                node._tree_index = len(self.nodes)
                self.nodes.append(node)
                for child in ast.iter_child_nodes(node):
                    child._depth = node._depth + 1

    def get_text_with_indentation(self, node):
        result = self.asttokens().get_text(node)
        
        if not result:
            if isinstance(node, FormattedValue):
                fvals = [
                    n for n in node.parent.values
                    if isinstance(n, FormattedValue)
                ]
                return '<f-string value{}>'.format(
                    optional_numeric_label(
                        fvals.index(node),
                        fvals,
                    )
                )
            else:
                return "<unknown>"
        
        if '\n' in result:
            result = ' ' * node.first_token.start[1] + result
            result = dedent(result)
        else:
            result = result.strip()
        return result


class Event(object):
    def __init__(self, frame_info, event, arg, depth, line_no=None):
        self.frame_info = frame_info
        self.frame = frame = frame_info.frame
        self.source = frame_info.source
        self.last_line_no = frame_info.last_line_no
        self.comprehension_type = frame_info.comprehension_type

        self.event = event
        self.arg = arg
        self.depth = depth

        self.variables = []
        if line_no is None:
            line_no = frame.f_lineno
        self.line_no = line_no
        self.code = frame.f_code

        if self.event == 'call' and self.source_line.lstrip().startswith('@'):
            # If a function decorator is found, skip lines until an actual
            # function definition is found.
            while True:
                self.line_no += 1
                try:
                    if self.source_line.lstrip().startswith('def'):
                        break
                except IndexError:
                    self.line_no = self.frame.lineno
                    break

    @property
    def source_line(self):
        return self.source.lines[self.line_no - 1]

    def code_qualname(self):
        return self.source.code_qualname(self.code)

    @property
    def opname(self):
        code_byte = self.code.co_code[self.frame.f_lasti]
        if not isinstance(code_byte, int):
            code_byte = ord(code_byte)
        return opcode.opname[code_byte]


def highlight_python(code):
    return code
    # TODO
    # import pygments
    # from pygments.formatters.terminal256 import Terminal256Formatter
    # from pygments.lexers.python import PythonLexer
    # return pygments.highlight(
    #     code,
    #     PythonLexer(),
    #     Terminal256Formatter(),
    # ).rstrip()


class DefaultFormatter(object):
    datetime_format = None

    def __init__(self, prefix='', columns='time', color=False):
        prefix = six.text_type(prefix)
        if prefix and prefix == prefix.rstrip():
            prefix += ' '
        self.prefix = prefix
        self.columns = [
            column if callable(column) else
            getattr(self, '{}_column'.format(column))
            for column in ensure_tuple(columns, split=True)
        ]
        self.column_widths = dict.fromkeys(self.columns, 0)
        if color:
            self.c = Colors
        else:
            self.c = NoColors()

    def thread_column(self, _event):
        return threading.current_thread().name

    def thread_ident_column(self, _event):
        return threading.current_thread().ident

    def time_column(self, _event):
        datetime_format = self.datetime_format or '%H:%M:%S.%f'
        result = datetime.now().strftime(datetime_format)
        if self.datetime_format is None:
            result = result[:-4]
        return result

    def file_column(self, event):
        return short_filename(event.code)

    def full_file_column(self, event):
        return event.code.co_filename

    def function_column(self, event):
        return event.code.co_name

    def function_qualname_column(self, event):
        return event.code_qualname()

    def full_prefix(self, event):
        return u'{c.grey}{self.prefix}{indent}{columns} {c.reset}'.format(
            c=self.c,
            self=self,
            indent=event.depth * u'    ',
            columns=self.columns_string(event),
        )

    def format(self, event):
        # type: (Event) -> str
        lines = []

        if event.event in ('call', 'enter'):
            lines += self.format_start(event)

        statements = event.source.statements
        this_statement = statements[event.line_no]
        last_statement = statements[event.last_line_no]
        statement_start_lines = self.get_statement_start_lines(event, this_statement, last_statement)

        lines += self.format_variables(event, last_statement)

        if event.event == 'return':
            lines += self.format_return(event)
        elif event.event == 'exception':
            lines += self.format_exception(event)
        elif event.event == 'enter':
            pass
        elif event.event == 'exit':
            lines += [u'{c.green}<<< Exit with block in {func}{c.reset}'.format(
                c=self.c,
                func=event.code_qualname(),
            )]
        else:
            if not (event.comprehension_type and event.event == 'line'):
                lines += statement_start_lines + [self.format_event(event)]

        return self.format_lines(event, lines)

    def format_exception(self, event):
        lines = []
        exception_string = ''.join(traceback.format_exception_only(*event.arg[:2]))
        lines += [
            u'{c.red}!!! {line}{c.reset}'.format(
                c=self.c,
                line=line,
            )
            for line in exception_string.splitlines()
        ]
        lines += self.format_executing_node_exception(event)
        return lines

    def format_return(self, event):
        # If a call ends due to an exception, we still get a 'return' event
        # with arg = None. This seems to be the only way to tell the difference
        # https://stackoverflow.com/a/12800909/2482744
        opname = event.opname
        arg = event.arg
        if arg is None:
            if opname == 'END_FINALLY':
                if event.frame_info.had_exception:
                    return [u'{c.red}??? Call either returned None or ended by exception{c.reset}'
                                .format(c=self.c)]
            elif opname not in ('RETURN_VALUE', 'YIELD_VALUE'):
                return [u'{c.red}!!! Call ended by exception{c.reset}'.format(c=self.c)]

        value = highlight_python(my_cheap_repr(arg))
        if event.comprehension_type:
            prefix = plain_prefix = u'Result: '
        else:
            plain_prefix = u'<<< {description} value from {func}: '.format(
                description='Yield' if opname == 'YIELD_VALUE' else 'Return',
                func=event.code_qualname(),
            )
            prefix = u'{c.green}{}{c.reset}'.format(
                plain_prefix,
                c=self.c,
            )
        return indented_lines(prefix, value, plain_prefix=plain_prefix)

    def get_statement_start_lines(self, event, this_statement, last_statement):
        result = []
        if (
                event.event != 'call' and
                this_statement and last_statement and
                this_statement != last_statement and
                this_statement.lineno != event.line_no and
                not isinstance(this_statement, try_statement)
        ):
            original_line_no = event.line_no
            for n in range(this_statement.lineno, original_line_no):
                event.line_no = n
                result.append(self.format_event(event))
            event.line_no = original_line_no
        return result

    def format_variables(self, event, last_statement):
        if last_statement:
            last_source_line = event.source.lines[last_statement.lineno - 1]
            dots = (get_leading_spaces(last_source_line)
                    .replace(' ', '.')
                    .replace('\t', '....'))
        else:
            dots = ''
            last_source_line = ''
        lines = []
        for var in event.variables:
            if ('{} = {}'.format(*var) != last_source_line.strip()
                    and not (
                            isinstance(last_statement, ast.FunctionDef)
                            and not last_statement.decorator_list
                            and var[0] == last_statement.name
                    )
            ):
                lines += self.format_variable(var, dots, event.comprehension_type)
        return lines

    def format_start(self, event):
        if event.comprehension_type:
            return ['{type}:'.format(type=event.comprehension_type)]
        else:
            if event.event == 'enter':
                description = 'Enter with block in'
            else:
                assert event.event == 'call'
                if event.frame_info.is_generator:
                    if event.opname == 'YIELD_VALUE':
                        description = 'Re-enter generator'
                    else:
                        description = 'Start generator'
                else:
                    description = 'Call to'
            return [
                u'{c.cyan}>>> {description} {c.reset}{name}{c.cyan} in {c.reset}File "{filename}", line {lineno}'.format(
                    name=event.code_qualname(),
                    filename=_get_filename(event),
                    lineno=event.line_no,
                    c=self.c,
                    description=description,
                )]

    def format_executing_node_exception(self, event):
        try:
            assert not NO_ASTTOKENS
            call = Source.executing(event.frame).node
            if not isinstance(call, ast.Call):
                return []

            if any(
                    getattr(call, attr, None)
                    for attr in 'args keywords starargs kwargs'.split()
            ):
                args_source = '...'
            else:
                args_source = ''

            source = '{func}({args})'.format(
                func=with_needed_parentheses(event.source.get_text_with_indentation(call.func)),
                args=args_source,
            )
            plain_prefix = '!!! When calling: '
            prefix = '{c.red}{}{c.reset}'.format(plain_prefix, c=self.c)
            return indented_lines(
                prefix,
                source,
                plain_prefix=plain_prefix
            )
        except Exception:
            return []

    def columns_string(self, event):
        column_strings = []
        for column in self.columns:
            string = six.text_type(column(event))
            width = self.column_widths[column] = max(
                self.column_widths[column],
                len(string),
            )
            column_strings.append(string.ljust(width))
        return u' '.join(column_strings)

    def format_event(self, entry):
        return u'{c.grey}{line_no:4}{c.reset} | {source_line}'.format(
            source_line=highlight_python(entry.source_line),
            c=self.c,
            **entry.__dict__
        )

    def format_variable(self, entry, dots, is_comprehension):
        name, value = entry
        if name.startswith('.') and name[1:].isdigit():
            description = 'Iterating over'
        elif is_comprehension:
            description = 'Values of {name}:'.format(name=name)
        else:
            description = '{name} ='.format(name=name)
        prefix = u'......{dots} {description} '.format(
            description=description,
            dots=dots,
        )
        return indented_lines(prefix, highlight_python(value))

    def format_line_only(self, event):
        return self.format_lines(event, [self.format_event(event)])

    def format_log(self, event):
        return self.format_lines(event, ['LOG:'])
    
    def format_log_value(self, event, source, value, depth):
        source_lines = indented_lines(
            u'....{} '.format(depth * 4 * '.'),
            source
        )
        lines = source_lines[:-1] + indented_lines(
            source_lines[-1] + ' = ',
            value,
        )
        return self.format_lines(event, lines)

    def format_lines(self, event, lines):
        prefix = self.full_prefix(event)
        return ''.join([
            (
                    prefix
                    + line
                    + u'\n'
            )
            for line in lines
        ])


def get_leading_spaces(s):
    return s[:len(s) - len(s.lstrip())]


def _get_filename(event):
    return event.code.co_filename


class NoColors(object):
    def __getattr__(self, item):
        return ''


class Colors(object):
    grey = '\x1b[90m'
    red = '\x1b[31m\x1b[1m'
    green = '\x1b[32m\x1b[1m'
    cyan = '\x1b[36m\x1b[1m'
    reset = '\x1b[0m'


def indented_lines(prefix, string, plain_prefix=None):
    lines = six.text_type(string).splitlines() or ['']
    return [prefix + lines[0]] + [
        ' ' * len(plain_prefix or prefix) + line
        for line in lines[1:]
    ]
