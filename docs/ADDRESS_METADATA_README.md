# MAIL Address Metadata System

## Overview

The MAIL (Multi-Agent Interface Layer) message system has been enhanced to include metadata about the type of addresses used in `sender` and `recipient` fields. This allows the system to distinguish between human users, AI agents, and system components.

## Address Types

The system now supports three distinct address types:

1. **`"agent"`** - AI agents and automated systems
2. **`"user"`** - Human users interacting with the system
3. **`"system"`** - System-level components and services

## Implementation Details

### MAILAddress Structure

Each address is now represented as a `MAILAddress` object with the following structure:

```python
class MAILAddress(TypedDict):
    address_type: Literal["agent", "user", "system"]
    address: str
```

### Helper Functions

The system provides several helper functions to create addresses with proper types:

- `create_agent_address(address: str) -> MAILAddress` - Creates an address for AI agents
- `create_user_address(address: str) -> MAILAddress` - Creates an address for human users  
- `create_system_address(address: str) -> MAILAddress` - Creates an address for system components
- `create_address(address: str, address_type: str) -> MAILAddress` - Generic address creation

### Utility Functions

For backward compatibility and data extraction:

- `get_address_string(address: MAILAddress | str) -> str` - Extracts the address string
- `get_address_type(address: MAILAddress | str) -> str` - Extracts the address type

## Usage Examples

### Creating Messages with Typed Addresses

```python
from src.mail.message import (
    MAILMessage, MAILRequest, create_agent_address, create_user_address
)

# Create a request from a user to an agent
request = MAILMessage(
    id="123",
    timestamp="2024-01-01T00:00:00Z",
    message=MAILRequest(
        task_id="task_123",
        request_id="req_123", 
        sender=create_user_address("john.doe@company.com"),
        recipient=create_agent_address("supervisor"),
        header="Help needed",
        body="I need assistance with analysis"
    ),
    msg_type="request"
)
```

### Extracting Address Information

```python
from src.mail.message import get_address_string, get_address_type

# Extract information from addresses
sender = request["message"]["sender"]
print(f"Sender: {get_address_string(sender)}")
print(f"Type: {get_address_type(sender)}")
# Output: Sender: john.doe@company.com, Type: user
```

## XML Output

The XML generation now includes address type metadata:

```xml
<incoming_message>
<timestamp>2024-01-01T00:00:00Z</timestamp>
<from type="user">john.doe@company.com</from>
<to type="agent">supervisor</to>
<header>Help needed</header>
<body>I need assistance with analysis</body>
</incoming_message>
```

## Backward Compatibility

The system maintains backward compatibility with existing code:

- Functions that previously accepted plain strings still work
- The `get_address_string()` and `get_address_type()` functions handle both old and new formats
- Plain strings are treated as agent addresses by default

## Migration Guide

### For Existing Code

1. **Immediate**: No changes required - existing code continues to work
2. **Recommended**: Update message creation to use typed addresses for better metadata
3. **Future**: Consider using the new helper functions for all new message creation

### For New Code

1. Use the appropriate `create_*_address()` functions for new messages
2. Leverage the address type metadata for routing and processing decisions
3. Use the utility functions to extract address information consistently

## Benefits

1. **Better Routing**: System can make intelligent decisions based on address types
2. **Enhanced Security**: Clear distinction between human users and automated systems
3. **Improved Logging**: Better audit trails with address type information
4. **Future Extensibility**: Foundation for more sophisticated address handling

## Example Scenarios

### Human User to AI Agent
```python
sender = create_user_address("user@company.com")
recipient = create_agent_address("analyst")
```

### AI Agent to AI Agent
```python
sender = create_agent_address("supervisor")
recipient = create_agent_address("analyst")
```

### System to All Agents
```python
sender = create_system_address("system")
recipients = [create_agent_address("supervisor"), create_agent_address("analyst")]
```

## Testing

Run the demonstration script to see the new system in action:

```bash
cd examples
python address_demo.py
```

This will show examples of creating messages with different address types and demonstrate the XML output with metadata.
