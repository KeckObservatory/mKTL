#!/usr/bin/env python3
"""
Parser to convert fakedcs_cake_config file to JSON format.

The parser extracts keyword definitions from the config file and creates
a JSON object mapping each keyword to its read and write channels.
"""

import json
import re
from pathlib import Path


def parse_cake_config(input_file, output_file=None):
    """
    Parse a cake configuration file and convert it to JSON.
    
    Args:
        input_file: Path to the input config file
        output_file: Path to the output JSON file (optional)
    
    Returns:
        dict: Parsed configuration as a dictionary
    """
    result = {}
    
    with open(input_file, 'r') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines and comments
        if not line or line.startswith('#'):
            i += 1
            continue
        
        # Skip configuration lines like "skip_num = 0", "prefix = fakedcs:"
        if '=' in line and not line.startswith(' '):
            i += 1
            continue
        
        # Check if this is a keyword definition line (starts with whitespace and contains "in")
        if line and not line.startswith('#') and ' in ' in line:
            # This is a keyword definition line - collect potentially multi-line description
            description_parts = [line.strip()]
            
            # Check if there are continuation lines (lines that don't contain mapping info)
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                # If the next line is empty, a comment, or looks like a mapping line (uppercase keyword), stop
                if not next_line or next_line.startswith('#'):
                    break
                # Check if it's a mapping line (starts with uppercase letters and has multiple columns)
                parts = next_line.split()
                if len(parts) >= 3 and parts[0].isupper():
                    # This is the mapping line
                    break
                # Otherwise, it's a continuation of the description
                description_parts.append(next_line)
                j += 1
            
            # Join all description parts
            full_description = ' '.join(description_parts)
            
            # Move to the mapping line first to check if it's ENMM type
            i = j
            if i < len(lines):
                mapping_line = lines[i].strip()
                
                # Parse the mapping line to extract the three channel names
                # Format: KEYWORD  READ_CHANNEL  WRITE_CHANNEL  COL4  COL5  TYPE  ...
                parts = mapping_line.split()
                
                if len(parts) >= 3:
                    keyword = parts[0].lower()  # First column (lowercase)
                    read_channel = parts[1]      # Second column
                    write_channel = parts[2]     # Third column
                    
                    # Check if column 4 (index 3) is ENMM to determine bitmask enumeration
                    is_bitmask = len(parts) >= 4 and parts[3] == 'ENMM'
                    
                    # Extract enumerators if present (inside curly braces)
                    enumerators = {}
                    enum_match = re.search(r'\{([^}]+)\}', full_description)
                    if enum_match:
                        enum_content = enum_match.group(1)
                        # Split by comma and clean up whitespace
                        enum_values = [v.strip() for v in enum_content.split(',')]
                        
                        if is_bitmask:
                            # For ENMM: use powers of 2 (0, 1, 2, 4, 8, 16, ...)
                            # First value is 0, second is 1, then powers of 2
                            for idx, val in enumerate(enum_values):
                                if idx == 0:
                                    key = "0"
                                elif idx == 1:
                                    key = "1"
                                else:
                                    key = str(2 ** (idx - 1))
                                enumerators[key] = val
                        else:
                            # For ENM: use sequential indices (0, 1, 2, 3, ...)
                            enumerators = {str(i): val for i, val in enumerate(enum_values)}
                    
                    # Extract units from the description (after "in")
                    units = ""
                    if ' in ' in full_description:
                        units_part = full_description.split(' in ', 1)[1]
                        # Remove curly braces and their contents if present
                        units = re.sub(r'\{[^}]*\}', '', units_part).strip()
                        # If units is empty or just quotes, set to empty string
                        if units in ['""', '']:
                            units = ""
                    
                    # Extract type from 6th column (index 5) if available
                    type_code = parts[5] if len(parts) >= 6 else ""
                    
                    # Map type codes to type names
                    type_map = {
                        'b': 'boolean',
                        'i': 'integer',
                        'd': 'double',
                        'em': 'enumerated',
                        'e': 'enumerated',
                        's': 'string'
                    }
                    data_type = type_map.get(type_code, type_code)
                    
                    entry = {
                        "read_channel": read_channel,
                        "write_channel": write_channel,
                        "description": full_description,
                        "units": {
                            "base": units,
                            "formatted": units
                        },
                        "type": data_type
                    }
                    
                    # Add enumerators only if they exist
                    if enumerators:
                        entry["enumerators"] = enumerators
                    
                    result[keyword] = entry
        
        i += 1
    
    # Write to output file if specified
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"Wrote {len(result)} entries to {output_file}")
    
    return result


def main():
    """Main entry point for the parser."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Convert cake config file to JSON format'
    )
    parser.add_argument(
        'input_file',
        help='Path to the input cake config file'
    )
    parser.add_argument(
        '-o', '--output',
        help='Path to the output JSON file (default: <input>.json)',
        default=None
    )
    
    args = parser.parse_args()
    
    # Determine output file name
    if args.output is None:
        input_path = Path(args.input_file)
        output_file = input_path.with_suffix('.json')
    else:
        output_file = args.output
    
    # Parse and convert
    result = parse_cake_config(args.input_file, output_file)
    
    # Print summary
    print(f"\nParsed {len(result)} keywords")
    print("\nFirst few entries:")
    for i, (key, value) in enumerate(result.items()):
        if i >= 3:
            break
        print(f"  {key}: {value}")


if __name__ == '__main__':
    main()
