"""
Contains the :class:`base class <tinydb.middlewares.Middleware>` for
middlewares and implementations.
"""
from typing import Optional, Callable
import logging
import time

from tinydb import Storage

logger = logging.getLogger(__name__)


class MiddlewareCircuitBreaker:
    """
    Circuit breaker for middleware chain execution.
    Tracks failures and implements graceful degradation.
    """
    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.is_open = False
    
    def record_success(self):
        """Record successful middleware execution."""
        self.failure_count = 0
        self.is_open = False
    
    def record_failure(self):
        """Record middleware execution failure."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.is_open = True
    
    def should_trip(self) -> bool:
        """Check if circuit breaker should trip (fail-open)."""
        if not self.is_open:
            return False
        if self.last_failure_time and time.time() - self.last_failure_time > self.timeout:
            self.is_open = False
            self.failure_count = 0
            return False
        return True


class Middleware:
    """
    The base class for all Middlewares.

    Middlewares hook into the read/write process of TinyDB allowing you to
    extend the behaviour by adding caching, logging, ...

    Your middleware's ``__init__`` method has to call the parent class
    constructor so the middleware chain can be configured properly.
    """

    def __init__(self, storage_cls) -> None:
        self._storage_cls = storage_cls
        self.storage: Storage = None  # type: ignore
        self._circuit_breaker = MiddlewareCircuitBreaker()
    
    def execute_safe(self, func: Callable, *args, **kwargs):
        """
        Execute middleware function with circuit breaker protection.
        
        :param func: Middleware function to execute
        :param args: Positional arguments
        :param kwargs: Keyword arguments
        :return: Function result or None if circuit is open
        """
        if self._circuit_breaker.should_trip():
            # Circuit is open - skip this middleware
            return None
        
        try:
            result = func(*args, **kwargs)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            self._circuit_breaker.record_failure()
            # Log failure but don't propagate - allow graceful degradation
            logger.warning(f'Middleware execution failed: {str(e)}')
            return None

    def __call__(self, *args, **kwargs):
        """
        Create the storage instance and store it as self.storage.

        Usually a user creates a new TinyDB instance like this::

            TinyDB(storage=StorageClass)

        The storage keyword argument is used by TinyDB this way::

            self.storage = storage(*args, **kwargs)

        As we can see, ``storage(...)`` runs the constructor and returns the
        new storage instance.


        Using Middlewares, the user will call::

                                       The 'real' storage class
                                       v
            TinyDB(storage=Middleware(StorageClass))
                       ^
        try:
                           Already an instance!

        So, when running ``self.storage = storage(*args, **kwargs)`` Python
        now will call ``__call__`` and TinyDB will expect the return value to
        be the storage (or Middleware) instance. Returning the instance is
        simple, but we also got the underlying (*real*) StorageClass as an
        __init__ argument that still is not an instance.
        So, we initialize it in __call__ forwarding any arguments we receive
        from TinyDB (``TinyDB(arg1, kwarg1=value, storage=...)``).

        In case of nested Middlewares, calling the instance as if it was a
        class results in calling ``__call__`` what initializes the next
        nested Middleware that itself will initialize the next Middleware and
        so on.
        """

        self.storage = self._storage_cls(*args, **kwargs)

        return self

    def read(self) -> str:
        """
        Read the storage.

        This is called when the database reads from the storage.
        The default implementation forwards the read call to the storage
        with exception isolation and context wrapping.
        """
        try:
            return self.storage.read()
        except Exception as e:
            # Wrap exception with middleware context for better debugging
            raise RuntimeError(
                f'Middleware read() failed in {self.__class__.__name__}: {str(e)}'
            ) from e

    def write(self, data: str) -> None:
        """
        Write to the storage.

        This is called when the database writes to the storage.
        The default implementation forwards the write call to the storage
        with exception isolation and context wrapping.
        """
        try:
            return self.storage.write(data)
        except Exception as e:
            # Wrap exception with middleware context for better debugging
            raise RuntimeError(
                f'Middleware write() failed in {self.__class__.__name__}: {str(e)}'
            ) from e

    def __getattr__(self, name):
        """
        Forward all unknown attribute calls to the underlying storage, so we
        remain as transparent as possible.
        """
        try:
            return getattr(self.__dict__['storage'], name)
        except (AttributeError, KeyError) as e:
            logger.warning(f'Middleware attribute access failed for {name}: {str(e)}')
            raise


class CachingMiddleware(Middleware):
    """
    Add some caching to TinyDB.

    This Middleware aims to improve the performance of TinyDB by writing only
    the last DB state every :attr:`WRITE_CACHE_SIZE` time and reading always
    from cache.
    """

    #: The number of write operations to cache before writing to disc
    WRITE_CACHE_SIZE = 1000

    def __init__(self, storage_cls):
        # Initialize the parent constructor
        super().__init__(storage_cls)

        # Prepare the cache
        self.cache = None
        self._cache_modified_count = 0

    def read(self):
        if self.cache is None:
            # Empty cache: read from the storage
            try:
                self.cache = self.storage.read()
            except Exception as e:
                logger.error(f'CachingMiddleware read() failed: {str(e)}')
                raise RuntimeError(
                    f'CachingMiddleware read() failed: {str(e)}'
                ) from e

        # Return the cached data
        return self.cache

    def write(self, data):
        # Store data in cache
        self.cache = data
        self._cache_modified_count += 1

        # Check if we need to flush the cache
        if self._cache_modified_count >= self.WRITE_CACHE_SIZE:
            self.flush()

    def flush(self):
        """
        Flush all unwritten data to disk.
        """
        if self._cache_modified_count > 0:
            # Force-flush the cache by writing the data to the storage
            self.storage.write(self.cache)
            self._cache_modified_count = 0

    def close(self):
        # Flush potentially unwritten data
        self.flush()

        # Let the storage clean up too
        self.storage.close()
