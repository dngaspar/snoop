import pysnooper


def foo():
    raise TypeError('bad')


def bar():
    try:
        foo()
    except Exception:
        str(1)
        raise


@pysnooper.snoop(depth=3)
def main():
    try:
        bar()
    except:
        pass


expected_output = """
12:34:56.789012 call        17 def main():
12:34:56.789012 line        18     try:
12:34:56.789012 line        19         bar()
    12:34:56.789012 call         8 def bar():
    12:34:56.789012 line         9     try:
    12:34:56.789012 line        10         foo()
        12:34:56.789012 call         4 def foo():
        12:34:56.789012 line         5     raise TypeError('bad')
        12:34:56.789012 exception    5     raise TypeError('bad')
        TypeError: bad
        Call ended by exception
    12:34:56.789012 exception   10         foo()
    TypeError: bad
    12:34:56.789012 line        11     except Exception:
    12:34:56.789012 line        12         str(1)
    12:34:56.789012 line        13         raise
    Call ended by exception
12:34:56.789012 exception   19         bar()
TypeError: bad
12:34:56.789012 line        20     except:
12:34:56.789012 line        21         pass
12:34:56.789012 return      21         pass
Return value:.. None
"""
