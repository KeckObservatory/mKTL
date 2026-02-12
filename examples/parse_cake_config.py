#!/usr/bin/env python3
"""
Parser to convert cake files to mktl JSON config format.

The parser extracts keyword definitions from the cake file and creates
a JSON object mapping each keyword to its read and write channels.
"""

import json
import re
from pathlib import Path


CAKE_BIN2ASCII_METHODS = bin2asc_mapping = {
    "R2D": {
        "function": "r2d_bin2asc",
        "description": "Radians to degrees",
        "bin_units": "Radians"
    },
    "R2D1": {
        "function": "r2d_bin2asc",
        "description": "Radians to degrees",
        "bin_units": "Radians"
    },
    "R2D2": {
        "function": "r2d_bin2asc",
        "description": "Radians to degrees",
        "bin_units": "Radians"
    },
    "RXD": {
        "function": "rxd_bin2asc",
        "description": "Radians to DMS",
        "bin_units": "Radians"
    },
    "RXH": {
        "function": "rxh_bin2asc",
        "description": "Radians to HMS",
        "bin_units": "Radians"
    },
    "RXH1": {
        "function": "rxh1_bin2asc",
        "description": "Radians to HMS with sign",
        "bin_units": "Radians"
    },
    "A2R": {
        "function": "a2r_bin2asc",
        "description": "Arcseconds to radians",
        "bin_units": "Arcseconds"
    },
    "M2A": {
        "function": "m2a_bin2asc",
        "description": "Meters to arcseconds (assumes f/15)",
        "bin_units": "Meters"
    },
    "M2A3": {
        "function": "m2a_bin2asc",
        "description": "Meters to arcseconds (assumes f/15)",
        "bin_units": "Meters"
    },
    "R2A": {
        "function": "r2a_bin2asc",
        "description": "Radians to arcseconds",
        "bin_units": "Radians"
    },
    "R2A2": {
        "function": "r2a_bin2asc",
        "description": "Radians to arcseconds",
        "bin_units": "Radians"
    },
    "R2A3": {
        "function": "r2a_bin2asc",
        "description": "Radians to arcseconds",
        "bin_units": "Radians"
    },
    "R2A4": {
        "function": "r2a_bin2asc",
        "description": "Radians to arcseconds",
        "bin_units": "Radians"
    },
    "R2S": {
        "function": "r2s_bin2asc",
        "description": "Radians to seconds of time",
        "bin_units": "Radians"
    },
    "R2S4": {
        "function": "r2s_bin2asc",
        "description": "Radians to seconds of time",
        "bin_units": "Radians"
    },
    "INT": {
        "function": "int_bin2asc",
        "description": "convert integer",
        "bin_units": "integer"
    },
    "BOO": {
        "function": "boo_bin2asc",
        "description": "convert boolean",
        "bin_units": "boolean"
    },
    "FLT": {
        "function": "flt_bin2asc",
        "description": "convert float",
        "bin_units": "float"
    },
    "DBL": {
        "function": "dbl_bin2asc",
        "description": "convert double",
        "bin_units": "double"
    },
    "DBL1": {
        "function": "dbl_bin2asc",
        "description": "convert double",
        "bin_units": "double"
    },
    "DBL2": {
        "function": "dbl_bin2asc",
        "description": "convert double",
        "bin_units": "double"
    },
    "DBL3": {
        "function": "dbl_bin2asc",
        "description": "convert double",
        "bin_units": "double"
    },
    "DBL4": {
        "function": "dbl_bin2asc",
        "description": "convert double",
        "bin_units": "double"
    },
    "M2CM": {
        "function": "m2cm_bin2asc",
        "description": "convert meters to centimeters",
        "bin_units": "meters"
    },
    "M2MM": {
        "function": "m2mm_bin2asc",
        "description": "convert meters to millimeters",
        "bin_units": "meters"
    },
    "M2UM": {
        "function": "m2um_bin2asc",
        "description": "convert meters to microns",
        "bin_units": "meters"
    },
    "STR": {
        "function": "str_bin2asc",
        "description": "convert string",
        "bin_units": "string"
    },
    "UTC": {
        "function": "utc_bin2asc",
        "description": "Seconds since 1970 to UT time of day (hh:mm:ss.ss)",
        "bin_units": "Seconds"
    },
    "DATE": {
        "function": "date_bin2asc",
        "description": "Seconds since 1970 to UT date (yyyy-mm-dd)",
        "bin_units": "Seconds"
    },
    "NOP": {
        "function": "nop_bin2asc",
        "description": "No conversion",
        "bin_units": ""
    },
    "ENM": {
        "function": "enm_bin2asc",
        "description": "convert binary to enumeration string",
        "bin_units": "binary"
    },
    "ENMM": {
        "function": "enmm_bin2asc",
        "description": "converts a single binary bit to the enumeration",
        "bin_units": "binary"
    },
    "MASK": {
        "function": "mask_bin2asc",
        "description": "convert binary to multiple bit mask",
        "bin_units": "binary"
    },
    "DT1": {
        "function": "dt1_bin2asc",
        "description": "rad-per-sec-to_s/hr",
        "bin_units": "rad-per-sec"
    },
    "DT2": {
        "function": "dt2_bin2asc",
        "description": "rad-per-sec-to-arcsec/hr",
        "bin_units": "rad-per-sec"
    }
}


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
    prefix = ""
    
    with open(input_file, 'r') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # find prefix line
        if line.startswith('prefix = '):
            prefix = line.split('=', 1)[1].strip()
            i += 1
            continue
        
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
                # Format: KEYWORD  READ_CHANNEL  WRITE_CHANNEL  BIN2ASCII_method ASCII2BIN_method TYPE  ...
                parts = mapping_line.split()
                
                if len(parts) >= 3:
                    keyword = parts[0].lower()  # First column (lowercase)
            
                    read_channel = prefix + parts[1]      # Second column
                    write_channel = prefix + parts[2]     # Third column
                    
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
                    f_units = ""
                    if ' in ' in full_description:
                        units_part = full_description.split(' in ', 1)[1]
                        # Remove curly braces and their contents if present
                        f_units = re.sub(r'\{[^}]*\}', '', units_part).strip()
                        # If units is empty or just quotes, set to empty string
                        if f_units in ['""', '']:
                            f_units = ""

                    bin2ascii_method = parts[3] if len(parts) >= 4 else ""
                    bin_units = ""
                    if bin2ascii_method in CAKE_BIN2ASCII_METHODS:
                        bin_units = CAKE_BIN2ASCII_METHODS[bin2ascii_method]['bin_units']

                    
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
                    
                    # Determine if we need to create separate entries
                    has_read = read_channel and read_channel.strip()
                    has_write = write_channel and write_channel.strip()
                    same_channel = has_read and has_write and read_channel == write_channel
                    
                    if same_channel:
                        # Same read/write channel - create one entry
                        entry = {
                            "channel": read_channel,
                            "gettable": True,
                            "settable": True,
                            "description": full_description,
                            "units": {
                                "": bin_units,
                                "formatted": f_units
                            },
                            "type": data_type
                        }
                        
                        # Add enumerators only if they exist
                        if enumerators:
                            entry["enumerators"] = enumerators
                        
                        result[keyword] = entry
                    
                    else:
                        # Different read/write channels - create separate entries
                        if has_read:
                            read_entry = {
                                "channel": read_channel,
                                "gettable": True,
                                "settable": False,
                                "description": full_description,
                                "units": {
                                    "": bin_units,
                                    "formatted": f_units
                                },
                                "type": data_type
                            }
                            
                            # Add enumerators only if they exist
                            if enumerators:
                                read_entry["enumerators"] = enumerators
                            
                            result[f"{keyword}:read"] = read_entry
                        
                        if has_write:
                            write_entry = {
                                "channel": write_channel,
                                "gettable": False,
                                "settable": True,
                                "description": full_description,
                                "units": {
                                    "": bin_units,
                                    "formatted": f_units
                                },
                                "type": data_type
                            }
                            
                            # Add enumerators only if they exist
                            if enumerators:
                                write_entry["enumerators"] = enumerators
                            
                            result[f"{keyword}:write"] = write_entry
        
        i += 1

    # Now we are going to merge duplicate channels (same channel name) into single entries. 
    # The name will be the channel name, and gettable/settable will be True if any of the duplicates had it True.

    merged_result = {}
    channels = [x['channel'] for x in result.values()]
    for key, entry in result.items():
        channel = entry['channel']
        if channels.count(channel) > 1:
            # Duplcate channel found - merge entries
            if channel in merged_result: # already merged
                continue
            # Find all entries with this channel
            same_channel_entries = [v for v in result.values() if v['channel'] == channel]
            merged_entry = {
                "channel": channel,
                "gettable": any(e.get('gettable', False) for e in same_channel_entries),
                "settable": any(e.get('settable', False) for e in same_channel_entries),
                "description": same_channel_entries[0]['description'], # take from first entry
                "units": same_channel_entries[0]['units'], # take from first entry
                "type": same_channel_entries[0]['type'] # take from first entry
            }
            merged_result[channel] = merged_entry
        else: # unique channel, just copy over
            merged_result[channel] = entry

    # Write to output file if specified
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(merged_result, f, indent=2)
        print(f"Wrote {len(result)} entries to {output_file}")
    
    return merged_result 


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
