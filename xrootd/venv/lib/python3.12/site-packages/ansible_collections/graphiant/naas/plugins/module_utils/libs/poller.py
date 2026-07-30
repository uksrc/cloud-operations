import functools
import sys
import time
import traceback

from .logger import setup_logger

# Required dependencies - checked when functions are called
# Don't raise at module level to allow import test to pass

LOG = setup_logger()


def raise_(exc_type, exc_value, exc_traceback):
    """Re-raise with traceback (Python 3)."""
    raise exc_value.with_traceback(exc_traceback)


def poller(timeout=60, wait=0.1, retries=None):
    """
    Returns a decorator that adds polling to the decorated function or method

    e.g.
    @poller(timeout=10, wait=1)
    def random_number_picker_max_timeout(number, numbers):
        if number != random.choice(numbers):
            raise AssertionError(f"Expected {number} to equal random choice")

    @poller(retries=5, wait=1)
    def random_number_picker_max_reties(number, numbers):
        if number != random.choice(numbers):
            raise AssertionError(f"Expected {number} to equal random choice")
    """

    def poller_decorator(fun):
        """
        Decorator that adds polling to the decorated function or method
        """

        @functools.wraps(fun)
        def timeout_poller(fun, timeout, wait, *fun_args, **fun_kwargs):
            """
            Wraps a function inside a timeout polling loop
            """
            start_time = time.time()
            attempt = 0
            exc = None
            while (time.time() - start_time) < timeout:
                remain = timeout - (time.time() - start_time)
                LOG.info("%s.%s(): attempt %s, time remaining %.2fs", fun.__module__, fun.__name__, attempt + 1, remain)
                try:
                    return fun(*fun_args, **fun_kwargs)
                except Exception as e:
                    exc = sys.exc_info()
                    LOG.info("Exception caught while calling method %s(): %r", fun.__name__, e)
                LOG.info("Sleeping for %s seconds before poller re-attempt...", wait)
                time.sleep(wait)
                attempt += 1
            if exc:
                LOG.warning("".join(traceback.format_exception(*exc)))
                raise_(exc[0], exc[1], exc[2])
            return False

        @functools.wraps(fun)
        def retry_poller(fun, retries, wait, *fun_args, **fun_kwargs):
            """
            Wraps a function inside a retry polling loop
            """
            exc = None
            for attempt in range(0, retries):
                LOG.info("Poller attempt: %s/%s", attempt + 1, retries)
                LOG.info("Calling method %s()...", fun.__name__)
                try:
                    return fun(*fun_args, **fun_kwargs)
                except Exception as e:
                    exc = sys.exc_info()
                    LOG.info("Exception caught while calling method %s(): %s", fun.__name__, e)
                LOG.info("Sleeping for %s seconds before retry...", wait)
                time.sleep(wait)
            if exc:
                LOG.warning("".join(traceback.format_exception(*exc)))
                raise_(exc[0], exc[1], exc[2])
            return False

        def pick_a_poller(*args, **kwargs):
            if retries is not None:
                return retry_poller(fun, retries, wait, *args, **kwargs)
            else:
                return timeout_poller(fun, timeout, wait, *args, **kwargs)

        # Return decorated function
        return pick_a_poller

    # Return decorator
    return poller_decorator
