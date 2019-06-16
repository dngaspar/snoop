import ast
import inspect
import pprint
import traceback
from copy import deepcopy
from uuid import uuid4

from snoop.formatting import Event, Source
from snoop.pycompat import builtins
from snoop.tracer import thread_global


class PP(object):
    def __init__(self, config):
        self.config = config

    def __call__(self, *args):
        if self.config.enabled:
            frame = inspect.currentframe().f_back
            self._pp(args, frame)

        if len(args) == 1:
            return args[0]
        else:
            return args

    def _pp(self, args, frame):
        depth = getattr(thread_global, 'depth', 0)
        event = Event(frame, 'log', None, depth)
        try:
            call = Source.executing(frame).node
            assert isinstance(call, ast.Call)
            assert len(args) == len(call.args)
        except Exception:
            arg_sources = [
                arg_source_placeholder(i, arg, args)
                for i, arg in enumerate(args)
            ]
        else:
            arg_sources = []
            for i, (call_arg, arg) in enumerate(zip(call.args, args)):
                if isinstance(call_arg, ast.Lambda):
                    arg_sources.extend(deep_pp(event, call_arg.body, frame))
                else:
                    try:
                        source = event.source.get_text_with_indentation(call_arg)
                    except Exception:
                        arg_source = arg_source_placeholder(i, arg, args)
                    else:
                        arg_source = root_arg_source(arg, source)
                    arg_sources.append(arg_source)
        formatted = self.config.formatter.format_log(event, arg_sources)
        self.config.write(formatted)


def root_arg_source(arg, source=None, args=None, i=None):
    if source is None:
        if len(args) == 1:
            source = '<argument>'
        else:
            source = '<argument {}>'.format(i + 1)
    return source, pprint.pformat(arg), 0


def arg_source_placeholder(i, arg, args):
    return root_arg_source(arg, args=args, i=i)


class NodeVisitor(ast.NodeTransformer):
    """
    This does the AST modifications that call the hooks.
    """

    def __init__(self, before_name, after_name):
        self.before_name = before_name
        self.after_name = after_name

    def generic_visit(self, node):
        # type: (ast.AST) -> ast.AST
        if (isinstance(node, ast.expr) and
                not (hasattr(node, "ctx") and not isinstance(node.ctx, ast.Load)) and
                not isinstance(node, getattr(ast, 'Starred', ()))):
            return self.visit_expr(node)
        return super(NodeVisitor, self).generic_visit(node)

    def visit_expr(self, node):
        # type: (ast.expr) -> ast.Call
        """
        each expression e gets wrapped like this:
            _treetrace_hidden_after_expr(_treetrace_hidden_before_expr(_tree_index), e)

        where the _treetrace_* functions are the corresponding methods with the
        TreeTracerBase and traced_file arguments already filled in (see _trace_methods_dict)
        """

        before_marker = ast.Call(
            func=ast.Name(id=self.before_name,
                          ctx=ast.Load()),
            args=[ast.Num(node._tree_index)],
            keywords=[],
        )

        ast.copy_location(before_marker, node)

        after_marker = ast.Call(
            func=ast.Name(id=self.after_name,
                          ctx=ast.Load()),
            args=[
                before_marker,
                super(NodeVisitor, self).generic_visit(node),
            ],
            keywords=[],
        )
        ast.copy_location(after_marker, node)
        ast.fix_missing_locations(after_marker)

        return after_marker


def deep_pp(event, call_arg, frame):
    arg_sources = []

    def before_expr(tree_index):
        node = event.source.nodes[tree_index]
        # TODO note node in case of exception
        return node

    before_expr.name = 'before_' + uuid4().hex

    def after_expr(node, value):
        source = event.source.get_text_with_indentation(node)

        try:
            ast.literal_eval(node)
        except ValueError:
            is_obvious = getattr(builtins, source, object()) == value
        else:
            is_obvious = True

        if not is_obvious:
            if call_arg is node:
                value_string = pprint.pformat(value)
            else:
                try:
                    value_string = repr(value)
                except Exception as e:
                    exception_string = ''.join(traceback.format_exception_only(type(e), e)).strip()
                    value_string = '<Exception in repr(): {}>'.format(exception_string)

            arg_sources.append([source, value_string, node._depth - call_arg._depth])
        return value

    after_expr.name = 'after_' + uuid4().hex

    new_node = deepcopy(call_arg)
    new_node = NodeVisitor(before_expr.name, after_expr.name).visit(new_node)
    expr = ast.Expression(new_node)
    ast.copy_location(expr, new_node)
    code = compile(expr, '<node>', 'eval')
    frame.f_globals[before_expr.name] = before_expr
    frame.f_globals[after_expr.name] = after_expr
    eval(code, frame.f_globals, frame.f_locals)
    frame.f_globals[before_expr.name] = lambda x: x
    frame.f_globals[after_expr.name] = lambda node, value: value

    return arg_sources
