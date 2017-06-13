import sys
import errno

if sys.version[0] == '2':
    class TimeoutError(OSError):
        def __init__(self, *args, **kwds):
            OSError.__init__(self, errno.ETIMEDOUT, *args, **kwds)
    import __builtin__ as builtins
else:
    import builtins
    TimeoutError = builtins.TimeoutError
