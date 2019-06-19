@snoop(depth=30)
def main():
    x = 1
    y = 2
    pp(pp(x + 1) + max(*pp(y + 2, y + 3)))
    assert pp.deep(lambda: x + 1 + max(y + 2, y + 3)) == 7

    lst = list(range(30))
    pp.deep(lambda: list(
        list(a + b for a in [1, 2])
        for b in [3, 4]
    ) + lst)
    pp(dict.fromkeys(range(30), 4))
    pp.deep(lambda: BadRepr() and 1)


class BadRepr(object):
    def __repr__(self):
        raise ValueError('bad')

main()

expected_output = """
12:34:56.78 >>> Call to main in File "/path/to_file.py", line 2
12:34:56.78    2 | def main():
12:34:56.78    3 |     x = 1
12:34:56.78    4 |     y = 2
12:34:56.78    5 |     pp(pp(x + 1) + max(*pp(y + 2, y + 3)))
12:34:56.78 LOG:
12:34:56.78 .... <argument> = 2
12:34:56.78 LOG:
12:34:56.78 .... <argument 1> = 4
12:34:56.78 .... <argument 2> = 5
12:34:56.78 LOG:
12:34:56.78 .... <argument> = 7
12:34:56.78    6 |     assert pp.deep(lambda: x + 1 + max(y + 2, y + 3)) == 7
12:34:56.78 LOG:
12:34:56.78 .... <argument> = 7
12:34:56.78    8 |     lst = list(range(30))
12:34:56.78 .......... lst = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, ..., 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29]
12:34:56.78 .......... len(lst) = 30
12:34:56.78    9 |     pp.deep(lambda: list(
12:34:56.78 LOG:
12:34:56.78 .... <argument> = [[4, 5],
12:34:56.78                    [5, 6],
12:34:56.78                    0,
12:34:56.78                    1,
12:34:56.78                    2,
12:34:56.78                    3,
12:34:56.78                    4,
12:34:56.78                    5,
12:34:56.78                    6,
12:34:56.78                    7,
12:34:56.78                    8,
12:34:56.78                    9,
12:34:56.78                    10,
12:34:56.78                    11,
12:34:56.78                    12,
12:34:56.78                    13,
12:34:56.78                    14,
12:34:56.78                    15,
12:34:56.78                    16,
12:34:56.78                    17,
12:34:56.78                    18,
12:34:56.78                    19,
12:34:56.78                    20,
12:34:56.78                    21,
12:34:56.78                    22,
12:34:56.78                    23,
12:34:56.78                    24,
12:34:56.78                    25,
12:34:56.78                    26,
12:34:56.78                    27,
12:34:56.78                    28,
12:34:56.78                    29]
12:34:56.78   13 |     pp(dict.fromkeys(range(30), 4))
12:34:56.78 LOG:
12:34:56.78 .... <argument> = {0: 4,
12:34:56.78                    1: 4,
12:34:56.78                    2: 4,
12:34:56.78                    3: 4,
12:34:56.78                    4: 4,
12:34:56.78                    5: 4,
12:34:56.78                    6: 4,
12:34:56.78                    7: 4,
12:34:56.78                    8: 4,
12:34:56.78                    9: 4,
12:34:56.78                    10: 4,
12:34:56.78                    11: 4,
12:34:56.78                    12: 4,
12:34:56.78                    13: 4,
12:34:56.78                    14: 4,
12:34:56.78                    15: 4,
12:34:56.78                    16: 4,
12:34:56.78                    17: 4,
12:34:56.78                    18: 4,
12:34:56.78                    19: 4,
12:34:56.78                    20: 4,
12:34:56.78                    21: 4,
12:34:56.78                    22: 4,
12:34:56.78                    23: 4,
12:34:56.78                    24: 4,
12:34:56.78                    25: 4,
12:34:56.78                    26: 4,
12:34:56.78                    27: 4,
12:34:56.78                    28: 4,
12:34:56.78                    29: 4}
12:34:56.78   14 |     pp.deep(lambda: BadRepr() and 1)
12:34:56.78 LOG:
12:34:56.78 .... <argument> = 1
12:34:56.78 <<< Return value from main: None
"""
