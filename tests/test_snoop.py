import io
import os
import re
import sys
import traceback
from importlib import import_module
from threading import current_thread

import pytest
import six
from cheap_repr import cheap_repr, register_repr
from cheap_repr.utils import safe_qualname
from littleutils import file_to_string, string_to_file
from python_toolbox import sys_tools, temp_file_tools

from snoop import formatting, install, spy
from snoop.configuration import Config
from snoop.pp_module import is_deep_arg
from snoop.utils import truncate_string, truncate_list, needs_parentheses, NO_ASTTOKENS

fix = 0

current_thread()._ident = current_thread()._Thread__ident = 123456789

formatting._get_filename = lambda _: "/path/to_file.py"

install()


@register_repr(type(cheap_repr))
def repr_function(func, _helper):
    return '<function %s at %#x>' % (
        safe_qualname(func), id(func))


@register_repr(type(sys))
def repr_module(module, _helper):
    return "<module '%s'>" % module.__name__


@register_repr(set)
def repr_set(x, helper):
    if not x:
        return repr(x)
    return helper.repr_iterable(x, '{', '}')


def sample_traceback():
    raw = ''.join(
        traceback.format_exception(*sys.exc_info())
    ).splitlines(True)
    tb = ''.join(
        line for line in raw
        if not line.strip().startswith("File")
        if not line.strip() == "raise value"  # part of six.reraise
    )
    sys.stderr.write(tb)


def assert_sample_output(module):
    with sys_tools.OutputCapturer(stdout=False,
                                  stderr=True) as output_capturer:
        assert sys.gettrace() is None
        module.main()
        assert sys.gettrace() is None

    time = '12:34:56.78'
    time_pattern = re.sub(r'\d', r'\\d', time)

    output = output_capturer.string_io.getvalue()

    normalised = re.sub(time_pattern, time, output).strip()
    normalised = re.sub(r'at 0x\w+>', 'at 0xABC>', normalised)
    normalised = normalised.replace('<genexpr>.<genexpr>', '<genexpr>')
    normalised = normalised.replace('<list_iterator', '<tupleiterator')
    normalised = normalised.replace('<listiterator', '<tupleiterator')
    normalised = normalised.replace('<tuple_iterator', '<tupleiterator')
    normalised = normalised.replace('<sequenceiterator', '<tupleiterator')

    try:
        assert (
                normalised ==
                module.expected_output.strip()
        )
    except AssertionError:
        if fix:
            path = module.__file__.rstrip('c')
            contents = file_to_string(path)
            match = re.search(
                r'expected_output = r?"""',
                contents,
            )
            contents = contents[:match.end(0)] + '\n{}\n"""\n'.format(normalised)
            string_to_file(contents, path)
        else:
            print('\n\nNormalised actual output:\n\n' + normalised)
            raise  # show pytest diff (may need -vv flag to see in full)


def test_samples():
    samples_dir = os.path.join(os.path.dirname(__file__), 'samples')
    for filename in os.listdir(samples_dir):
        if filename.endswith('.pyc'):
            continue
        module_name = six.text_type(filename.split('.')[0])

        if module_name in '__init__ __pycache__':
            continue

        if module_name in 'django_sample' and six.PY2:
            continue
    
        if NO_ASTTOKENS:
            if module_name in 'pandas_sample spy pp pp_exception enabled exception color':
                continue
        else:
            if module_name.startswith('no_asttokens'):
                continue

        if module_name in 'f_string' and sys.version_info[:2] < (3, 6):
            continue

        module = import_module('tests.samples.' + module_name)
        assert_sample_output(module)


def test_string_io():
    string_io = io.StringIO()
    config = Config(out=string_io)
    contents = u'stuff'
    config.write(contents)
    assert string_io.getvalue() == contents


def test_callable():
    string_io = io.StringIO()

    def write(msg):
        string_io.write(msg)

    string_io = io.StringIO()
    config = Config(out=write)
    contents = u'stuff'
    config.write(contents)
    assert string_io.getvalue() == contents


def test_file_output():
    with temp_file_tools.create_temp_folder(prefix='snoop') as folder:
        path = folder / 'foo.log'

        config = Config(out=path)
        contents = u'stuff'
        config.write(contents)
        with path.open() as output_file:
            output = output_file.read()
        assert output == contents


def test_no_overwrite_by_default():
    with temp_file_tools.create_temp_folder(prefix='snoop') as folder:
        path = folder / 'foo.log'
        with path.open('w') as output_file:
            output_file.write(u'lala')
        config = Config(str(path))
        config.write(u' doo be doo')
        with path.open() as output_file:
            output = output_file.read()
        assert output == u'lala doo be doo'


def test_overwrite():
    with temp_file_tools.create_temp_folder(prefix='snoop') as folder:
        path = folder / 'foo.log'
        with path.open('w') as output_file:
            output_file.write(u'lala')

        config = Config(out=str(path), overwrite=True)
        config.write(u'doo be')
        config.write(u' doo')

        with path.open() as output_file:
            output = output_file.read()
        assert output == u'doo be doo'


def test_error_in_overwrite_argument():
    with pytest.raises(Exception, match='can only be used when writing'):
        Config(overwrite=True)


def test_needs_parentheses():
    assert not needs_parentheses('x')
    assert not needs_parentheses('x.y')
    assert not needs_parentheses('x.y.z')
    assert not needs_parentheses('x.y.z[0]')
    assert not needs_parentheses('x.y.z[0]()')
    assert not needs_parentheses('x.y.z[0]()(3, 4 * 5)')
    assert not needs_parentheses('foo(x)')
    assert not needs_parentheses('foo(x+y)')
    assert not needs_parentheses('(x+y)')
    assert not needs_parentheses('[x+1 for x in ()]')
    assert needs_parentheses('x + y')
    assert needs_parentheses('x * y')
    assert needs_parentheses('x and y')
    assert needs_parentheses('x if z else y')


def test_truncate_string():
    max_length = 20
    for i in range(max_length * 2):
        string = i * 'a'
        truncated = truncate_string(string, max_length)
        if len(string) <= max_length:
            assert string == truncated
        else:
            assert truncated == 'aaaaaaaa...aaaaaaaaa'
            assert len(truncated) == max_length


def test_truncate_list():
    max_length = 5
    for i in range(max_length * 2):
        lst = i * ['a']
        truncated = truncate_list(lst, max_length)
        if len(lst) <= max_length:
            assert lst == truncated
        else:
            assert truncated == ['a', 'a', '...', 'a', 'a']
            assert len(truncated) == max_length


class Foo(object):
    def bar1(self):
        pass

    @staticmethod
    def bar2():
        pass


def test_is_deep_arg():
    assert is_deep_arg(lambda: 0)
    assert not is_deep_arg(lambda x: 0)
    assert not is_deep_arg(lambda x=None: 0)
    assert not is_deep_arg(lambda *x: 0)
    assert not is_deep_arg(lambda **x: 0)
    assert not is_deep_arg(test_is_deep_arg)
    assert not is_deep_arg(Foo)
    assert not is_deep_arg(Foo.bar1)
    assert not is_deep_arg(Foo().bar1)
    assert not is_deep_arg(Foo.bar2)
    assert not is_deep_arg(Foo().bar2)


def test_no_asttokens_spy():
    if NO_ASTTOKENS:
        with pytest.raises(Exception, match="birdseye doesn't support this version of Python"):
            spy(test_is_deep_arg)
