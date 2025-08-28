
from google.protobuf.json_format import ParseDict, MessageToDict
from google.protobuf.struct_pb2 import Struct


# Convert a Python dictionary to a Struct
def dict_to_struct(data):
    if not isinstance(data, dict):
        raise ValueError("Input must be a dictionary.")
    struct_obj = Struct()
    ParseDict(data, struct_obj)  # ParseDict handles the conversion
    return struct_obj

# Convert a Struct back to a Python dictionary
def struct_to_dict(struct_obj):
    if not isinstance(struct_obj, Struct):
        raise ValueError("Input must be a Struct object.")
    return MessageToDict(struct_obj)  # MessageToDict handles the conversion

# Example usage
if __name__ == "__main__":
    # Example dictionary
    example_dict = {
        "name": "Alice",
        "age": 30,
        "is_active": True,
        "preferences": {
            "language": "Python",
            "framework": "Django"
        },
        "scores": [95, 88, 76]
    }

    # Convert dict to Struct
    struct_obj = dict_to_struct(example_dict)
    print("Struct object:")
    print(struct_obj)

    # Convert Struct back to dict
    converted_dict = struct_to_dict(struct_obj)
    print("\nConverted back to dictionary:")
    print(converted_dict)
