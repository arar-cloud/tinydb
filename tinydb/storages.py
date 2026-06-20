"""
Contains the :class:`base class <tinydb.storages.Storage>` for storages and
implementations.
"""

import errno
import io
import json
import os
import time
import warnings
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union

__all__ = ('Storage', 'JSONStorage', 'MemoryStorage')


def touch(path: str, create_dirs: bool) -> None:
    """
    Create a file if it doesn't exist yet.

    :param path: The file to create.
    :param create_dirs: Whether to create all missing parent directories.
    """
    if create_dirs:
        base_dir = os.path.dirname(path)

        # Check if we need to create missing parent directories
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

    # Create the file by opening it in 'a' mode which creates the file if it
    # does not exist yet but does not modify its contents
    with open(path, 'a'):
        pass


class Storage(ABC):
    """
    The abstract base class for all Storages.

    A Storage (de)serializes the current state of the database and stores it in
    some place (memory, file on disk, ...).
    """

    # Using ABCMeta as metaclass allows instantiating only storages that have
    # implemented read and write

    @abstractmethod
    def read(self) -> Optional[Dict[str, Dict[str, Any]]]:  # type: ignore[override]
        """
        Read the current state.

        Any kind of deserialization should go here.

        Return ``None`` here to indicate that the storage is empty.
        """

        raise NotImplementedError('To be overridden!')

    @abstractmethod
    def write(self, data: Dict[str, Dict[str, Any]]) -> None:
        """
        Write the current state of the database to the storage.

        Any kind of serialization should go here.

        :param data: The current state of the database.
        """

        raise NotImplementedError('To be overridden!')

    def close(self) -> None:
        """
        Optional: Close open file handles, etc.
        """

        pass


class JSONStorage(Storage):
    """
    Store the data in a JSON file.
    """

    def __init__(
        self,
        path: str,
        create_dirs: bool = False,
        encoding: Optional[str] = None,
        access_mode: str = 'r+',
        **kwargs,
    ) -> None:
        """
        Create a new instance.

        Also creates the storage file, if it doesn't exist and the access mode
        is appropriate for writing.

        **Note:** Using an access mode other than `r` or `r+` will probably
        lead to data loss or data corruption!

        **Note:** **Never** pass untrusted or user-controlled code as ``kwargs``
        members like ``cls`` or ``default`` will be called on every write
        operation.

        :param path: Where to store the JSON data.
        :param access_mode: mode in which the file is opened (r, r+)
        :type access_mode: str
        """

        super().__init__()

        self._mode = access_mode
        self.kwargs = kwargs

        if access_mode not in ('r', 'rb', 'r+', 'rb+'):
            warnings.warn(
                'Using an `access_mode` other than \'r\', \'rb\', \'r+\' '
                'or \'rb+\' can cause data loss or corruption'
            )

        # Create the file if it doesn't exist and creating is allowed by the
        # access mode
        if any([character in self._mode for character in ('+', 'w', 'a')]):  # any of the writing modes
            touch(path, create_dirs=create_dirs)

        # Open the file for reading/writing
        self._handle = open(path, mode=self._mode, encoding=encoding)

    def close(self) -> None:
        self._handle.close()

    def read(self) -> Optional[Dict[str, Dict[str, Any]]]:
        # Read JSON data with retry logic for transient I/O failures.
        # Retries transient failures (file locks, EMFILE, temporary unavailability).
        # Immediately propagates permanent failures (permission, not found, corruption).
        max_retries = 3
        initial_delay_ms = 100
        max_delay_ms = 5000
        jitter_fraction = 0.1
        
        for attempt in range(max_retries + 1):
            try:
                # Get the file size by moving the cursor to the file end
                self._handle.seek(0, os.SEEK_END)
                size = self._handle.tell()

                if not size:
                    # File is empty, initialize database
                    return None
                
                # Return to beginning and load JSON
                self._handle.seek(0)
                return json.load(self._handle)
                
            except (PermissionError, FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
                # Permanent failures: fail immediately
                raise
            except (IOError, OSError) as e:
                # Classify transient vs permanent by errno
                transient_errors = {errno.EAGAIN, errno.EWOULDBLOCK, errno.EMFILE, errno.ENFILE}
                is_transient = getattr(e, 'errno', None) in transient_errors or 'lock' in str(e).lower()
                
                if not is_transient or attempt >= max_retries:
                    raise
                
                # Exponential backoff with jitter for transient failures
                delay_ms = min(initial_delay_ms * (2 ** attempt), max_delay_ms)
                jitter = delay_ms * jitter_fraction * (0.5 if attempt % 2 else -0.5)
                sleep_time = (delay_ms + jitter) / 1000.0
                time.sleep(max(0, sleep_time))

    def write(self, data: Dict[str, Dict[str, Any]]) -> None:  # type: ignore[override]
        # Write JSON data with retry logic for transient I/O failures.
        # Retries transient failures (file locks, EMFILE, ENOMEM, temporary unavailability).
        # Immediately propagates permanent failures (permission, disk full, type errors).
        # Uses atomic writes (seek/write/flush/fsync/truncate) ensuring idempotency.
        max_retries = 3
        initial_delay_ms = 100
        max_delay_ms = 5000
        jitter_fraction = 0.1
        
        for attempt in range(max_retries + 1):
            try:
                # Move cursor to beginning
                self._handle.seek(0)
                
                # Serialize the database state
                serialized = json.dumps(data, **self.kwargs)
                
                # Write the serialized data
                self._handle.write(serialized)
                
                # Ensure written to disk (atomic semantics)
                self._handle.flush()
                os.fsync(self._handle.fileno())
                
                # Truncate file if it got shorter
                self._handle.truncate()
                return
                
            except io.UnsupportedOperation:
                raise IOError('Cannot write to the database. Access mode is "{0}"'.format(self._mode))
            except (PermissionError, TypeError) as e:
                # Permanent failures: permission denied, type error
                raise
            except OSError as e:
                # Permanent: disk full (ENOSPC)
                if getattr(e, 'errno', None) == errno.ENOSPC:
                    raise
                # Transient: EMFILE, ENFILE, ENOMEM, EAGAIN, EWOULDBLOCK
                transient_errors = {errno.EAGAIN, errno.EWOULDBLOCK, errno.EMFILE, errno.ENFILE, errno.ENOMEM}
                is_transient = getattr(e, 'errno', None) in transient_errors or 'lock' in str(e).lower()
                
                if not is_transient or attempt >= max_retries:
                    raise
                
                # Exponential backoff with jitter for transient failures
                delay_ms = min(initial_delay_ms * (2 ** attempt), max_delay_ms)
                jitter = delay_ms * jitter_fraction * (0.5 if attempt % 2 else -0.5)
                sleep_time = (delay_ms + jitter) / 1000.0
                time.sleep(max(0, sleep_time))
            except IOError as e:
                # Transient: file lock, resource contention
                is_transient = 'lock' in str(e).lower() or getattr(e, 'errno', None) in {errno.EAGAIN, errno.EWOULDBLOCK}
                
                if not is_transient or attempt >= max_retries:
                    raise
                
                # Exponential backoff with jitter
                delay_ms = min(initial_delay_ms * (2 ** attempt), max_delay_ms)
                jitter = delay_ms * jitter_fraction * (0.5 if attempt % 2 else -0.5)
                sleep_time = (delay_ms + jitter) / 1000.0
                time.sleep(max(0, sleep_time))


class MemoryStorage(Storage):
    """
    Store the data as JSON in memory.
    """

    def __init__(self) -> None:
        """
        Create a new instance.
        """

        super().__init__()
        self.memory = None

    def read(self) -> Optional[Dict[str, Dict[str, Any]]]:
        return self.memory

    def write(self, data: Dict[str, Dict[str, Any]]):
        self.memory = data
