# TinyDB Security Hardening Guide

This document outlines the security measures implemented in TinyDB to protect against common vulnerabilities and attack vectors.

## Security Features

### 1. Input Validation and Sanitization

#### File Path Validation
- **Purpose**: Prevent directory traversal attacks
- **Implementation**: `tinydb/security.py:validate_file_path()`
- **Features**:
  - Rejects paths containing `..` sequences
  - Detects and rejects null bytes
  - Validates paths are within specified base directories
  - Resolves paths to absolute form for comparison

**Usage Example**:
```python
from tinydb.security import validate_file_path

# This will raise SecurityError
try:
    path = validate_file_path("../../../etc/passwd")
except SecurityError:
    print("Path validation failed")

# This is safe
path = validate_file_path("/var/lib/tinydb/database.json")
```

#### Document Validation
- **Purpose**: Prevent oversized documents and DoS attacks
- **Implementation**: `tinydb/security.py:validate_document_size()`
- **Limits**:
  - Maximum document size: 10 MB (configurable)
  - Maximum database size: 1 GB (configurable)

**Usage Example**:
```python
from tinydb.security import validate_document_size

# This will raise SecurityError if too large
doc = {"data": "x" * 20_000_000}  # 20MB
try:
    validate_document_size(doc)
except SecurityError:
    print("Document exceeds size limit")
```

### 2. Document ID Immutability

#### ID Validation
- **Purpose**: Prevent ID spoofing and forgery
- **Implementation**: `tinydb/security.py:validate_document_id()`
- **Guarantees**:
  - Document IDs must be positive integers
  - IDs are immutable post-creation
  - Sequential ID generation prevents collisions

**Usage Example**:
```python
from tinydb.security import validate_document_id

# Valid ID
validate_document_id(1)  # OK

# Invalid IDs
try:
    validate_document_id(0)      # SecurityError
    validate_document_id(-1)     # SecurityError
    validate_document_id("123")  # SecurityError
except SecurityError:
    print("Invalid document ID")
```

### 3. Injection Attack Prevention

#### JSON Sanitization
- **Purpose**: Prevent injection through document content
- **Implementation**: `tinydb/security.py:sanitize_json_input()`
- **Features**:
  - Strict JSON parsing with `strict=True` flag
  - Rejects non-object root elements
  - Detects dangerous key patterns (`__`, `eval`, `exec`, etc.)
  - Enforces maximum key length

**Usage Example**:
```python
from tinydb.security import sanitize_json_input, SecurityError

# Safe JSON
try:
    data = sanitize_json_input('{"name": "Alice", "age": 30}')
    print(data)  # {'name': 'Alice', 'age': 30}
except SecurityError:
    print("Invalid JSON")

# Dangerous JSON (rejected)
dangerous = '{"__import__": "os"}'
try:
    sanitize_json_input(dangerous)
except SecurityError:
    print("Dangerous key pattern detected")
```

#### Query Operation Validation
- **Purpose**: Prevent code injection through query parameters
- **Implementation**: `tinydb/operations_security_reference.py:SafeOperationValidator`
- **Features**:
  - Whitelist of allowed operations (eq, ne, lt, le, gt, ge, in, contains, etc.)
  - Rejects lambda functions and anonymous callables
  - Detects dangerous function names (eval, exec, system, etc.)
  - Validates query parameters for suspicious patterns

**Usage Example**:
```python
from tinydb.operations_security_reference import SafeOperationValidator, SecurityError

# Safe operation
try:
    SafeOperationValidator.validate_operation_type('eq')
    print("Operation allowed")
except SecurityError:
    print("Operation not allowed")

# Dangerous operation (rejected)
try:
    SafeOperationValidator.validate_operation_type('eval')
except SecurityError:
    print("Dangerous operation detected")

# Lambda functions are rejected
try:
    SafeOperationValidator.validate_operation_callable(lambda x: x > 5)
except SecurityError:
    print("Lambda functions not allowed")
```

### 4. Table Name Validation

- **Purpose**: Prevent table name injection attacks
- **Implementation**: `tinydb/security.py:validate_table_name()`
- **Rules**:
  - Only alphanumeric characters, underscores, and dashes allowed
  - Maximum length: 255 characters
  - Cannot be empty

**Usage Example**:
```python
from tinydb.security import validate_table_name, SecurityError

# Valid table names
valid_names = ['users', 'user_data', 'data-backup']
for name in valid_names:
    validate_table_name(name)  # OK

# Invalid table names (rejected)
invalid = ['users;DROP TABLE--', 'table@name', 'table name']
for name in invalid:
    try:
        validate_table_name(name)
    except SecurityError:
        print(f"Invalid table name: {name}")
```

### 5. File Permission Management

#### Secure Permissions
- **Purpose**: Prevent unauthorized access to database files
- **Implementation**: `tinydb/database_security_reference.py:SecureFilePermissions`
- **Configuration**:
  - Database files created with mode `0o600` (owner read/write only)
  - No group or other access permissions

**Usage Example**:
```python
from pathlib import Path
from tinydb.database_security_reference import SecureFilePermissions

db_file = Path('/var/lib/tinydb/database.json')

# Ensure secure permissions
SecureFilePermissions.ensure_secure_permissions(db_file)

# Verify permissions are secure
if SecureFilePermissions.verify_secure_permissions(db_file):
    print("File permissions are secure")
else:
    print("Warning: File permissions are not secure")
```

## Security Testing

Comprehensive security tests are included in `tests/test_security.py` covering:

- **Path Traversal Tests** (`@pytest.mark.traversal`):
  - Directory traversal prevention
  - Null byte rejection
  - Base directory confinement

- **Injection Attack Tests** (`@pytest.mark.injection`):
  - JSON injection prevention
  - Query parameter validation
  - Dangerous key detection

- **Document ID Tests** (`@pytest.mark.immutability`):
  - ID immutability enforcement
  - Type validation
  - Range validation

- **Denial of Service Tests** (`@pytest.mark.dos`):
  - Document size limits
  - Database size limits
  - Memory exhaustion prevention

- **Input Validation Tests** (`@pytest.mark.validation`):
  - Table name validation
  - Parameter sanitization
  - Format verification

### Running Security Tests

```bash
# Run all security tests
pytest -m security

# Run specific security test categories
pytest -m traversal      # Path traversal tests
pytest -m injection      # Injection attack tests
pytest -m immutability   # Document ID immutability tests
pytest -m dos           # Denial of service tests
pytest -m validation    # Input validation tests

# Run with coverage
pytest -m security --cov=tinydb --cov-report=html
```

## Security Best Practices for TinyDB Users

### 1. File System Security

```python
from pathlib import Path
from tinydb import TinyDB
from tinydb.database_security_reference import SecureFilePermissions

# Create database in secure location
db_path = Path('/var/lib/tinydb/app.json')
db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

# Open database
db = TinyDB(str(db_path))

# Ensure permissions are secure
SecureFilePermissions.ensure_secure_permissions(db_path)
```

### 2. Input Validation

```python
from tinydb import TinyDB
from tinydb.security import (
    validate_document_size,
    validate_table_name,
    validate_document_id,
)

db = TinyDB('db.json')

# Validate document before insertion
doc = {"name": "Alice", "email": "alice@example.com"}
validate_document_size(doc)

# Validate table names
table_name = "users"
validate_table_name(table_name)
users = db.table(table_name)

# Validate document IDs
for doc_id in [1, 2, 3]:
    validate_document_id(doc_id)
```

### 3. Query Construction

```python
from tinydb import TinyDB, Query
from tinydb.operations_security_reference import SafeOperationValidator

db = TinyDB('db.json')
Users = db.table('users')

# Use Query object with safe operations
User = Query()

# Safe queries (recommended)
results = Users.search(User.age > 18)  # Range comparison
results = Users.search(User.name == "Alice")  # Equality
results = Users.search(User.status.in_(['active', 'pending']))  # In list

# Avoid: Direct string queries or lambda functions
# This would be rejected by security validation:
# results = Users.search(User.custom_fn())  # Lambda not allowed
```

### 4. Database Maintenance

```python
from pathlib import Path
from tinydb import TinyDB
from tinydb.database_security_reference import SecureFilePermissions

db_path = Path('database.json')
db = TinyDB(str(db_path))

# Periodic security checks
if not SecureFilePermissions.verify_secure_permissions(db_path):
    print("Warning: Database file permissions need attention")
    SecureFilePermissions.ensure_secure_permissions(db_path)

# Regular backups with secure permissions
import shutil
backup_path = Path('database.json.backup')
shutil.copy2(str(db_path), str(backup_path))
SecureFilePermissions.ensure_secure_permissions(backup_path)
```

## Deployment Recommendations

### 1. Environment Setup

- Store database files in a dedicated directory with restricted permissions
- Run TinyDB with least privilege (dedicated user account if possible)
- Enable file system auditing for database file access
- Use AppArmor or SELinux profiles to restrict database file access

### 2. Access Control

```bash
# Create dedicated directory
sudo mkdir -p /var/lib/tinydb
sudo chown tinydb:tinydb /var/lib/tinydb
sudo chmod 700 /var/lib/tinydb

# Database files should have restrictive permissions
sudo chmod 600 /var/lib/tinydb/database.json
sudo chown tinydb:tinydb /var/lib/tinydb/database.json
```

### 3. Monitoring and Logging

- Monitor database file access patterns
- Log security validation failures
- Alert on permission changes
- Regular backup verification

### 4. Updates and Maintenance

- Keep TinyDB updated with security patches
- Review and test security updates in staging environment
- Monitor security advisories
- Maintain audit logs of database operations

## Security Limitations

TinyDB's security hardening provides defense-in-depth protection, but has inherent limitations:

1. **Single-Process Design**: TinyDB is designed for single-process access. Multi-process/distributed scenarios require additional coordination.

2. **Local File Storage**: Security depends on underlying file system permissions. Network storage may have different security considerations.

3. **No Built-in Encryption**: Database files are stored in plaintext. Use file system encryption (dm-crypt, BitLocker, etc.) for sensitive data.

4. **No Authentication/Authorization**: TinyDB has no built-in user authentication. Implement at application level.

5. **No Audit Logging**: Application-level logging is required for compliance and forensics.

## Security Incident Response

If you discover a security vulnerability in TinyDB:

1. **Do not** open a public issue
2. Email details to security contact (found in SECURITY.rst)
3. Allow time for patch development
4. Coordinate disclosure timeline

## References

- [OWASP: Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal)
- [OWASP: Injection](https://owasp.org/www-project-top-ten/)
- [OWASP: Denial of Service](https://owasp.org/www-community/attacks/Denial_of_Service)
- [CWE-22: Improper Limitation of a Pathname to a Restricted Directory](https://cwe.mitre.org/data/definitions/22.html)
- [CWE-94: Improper Control of Generation of Code](https://cwe.mitre.org/data/definitions/94.html)
