#!/usr/bin/env python3
import struct

def parse_po_file(filename):
    """Parse PO file and return list of (msgid, msgstr) pairs"""
    entries = []
    
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip comments and empty lines
        if line.startswith('#') or line == '':
            i += 1
            continue
        
        # Look for msgid
        if line.startswith('msgid '):
            # Extract msgid
            msgid = line[7:-1]  # Remove 'msgid ' and quotes
            i += 1
            
            # Handle multiline msgid
            while i < len(lines) and lines[i].strip().startswith('"'):
                msgid += lines[i].strip()[1:-1]  # Remove quotes
                i += 1
            
            # Look for msgstr
            if i < len(lines) and lines[i].strip().startswith('msgstr '):
                msgstr = lines[i].strip()[8:-1]  # Remove 'msgstr ' and quotes
                i += 1
                
                # Handle multiline msgstr
                while i < len(lines) and lines[i].strip().startswith('"'):
                    msgstr += lines[i].strip()[1:-1]  # Remove quotes
                    i += 1
                
                # Skip header (empty msgid)
                if msgid.strip():
                    entries.append((msgid, msgstr))
            else:
                # No msgstr found
                if msgid.strip():
                    entries.append((msgid, ''))
        else:
            i += 1
    
    return entries

def compile_po_to_mo(po_file, mo_file):
    """Compile PO to MO file"""
    entries = parse_po_file(po_file)
    
    print(f"Found {len(entries)} entries")
    
    # Calculate offsets
    num_entries = len(entries)
    orig_table_offset = 28
    trans_table_offset = orig_table_offset + num_entries * 8
    
    # Prepare strings
    orig_strings = [msg.encode('utf-8') for msg, _ in entries]
    trans_strings = [trans.encode('utf-8') for _, trans in entries]
    
    # Calculate offsets
    strings_offset = trans_table_offset + num_entries * 8
    current_offset = strings_offset
    
    orig_offsets = []
    trans_offsets = []
    
    for i in range(num_entries):
        orig_len = len(orig_strings[i])
        trans_len = len(trans_strings[i])
        
        orig_offsets.append((orig_len, current_offset))
        current_offset += orig_len + 1
        
        trans_offsets.append((trans_len, current_offset))
        current_offset += trans_len + 1
    
    # Write MO file
    with open(mo_file, 'wb') as f:
        # Header
        f.write(struct.pack('<I', 0x950412de))
        f.write(struct.pack('<I', 0))
        f.write(struct.pack('<I', num_entries))
        f.write(struct.pack('<I', orig_table_offset))
        f.write(struct.pack('<I', trans_table_offset))
        f.write(struct.pack('<I', 0))
        f.write(struct.pack('<I', 0))
        
        # Tables
        for length, offset in orig_offsets:
            f.write(struct.pack('<I', length))
            f.write(struct.pack('<I', offset))
        
        for length, offset in trans_offsets:
            f.write(struct.pack('<I', length))
            f.write(struct.pack('<I', offset))
        
        # String data
        for orig_str in orig_strings:
            f.write(orig_str)
            f.write(b'\x00')
        
        for trans_str in trans_strings:
            f.write(trans_str)
            f.write(b'\x00')
    
    print(f"Successfully compiled {num_entries} entries to {mo_file}")

if __name__ == '__main__':
    compile_po_to_mo('locale/de/LC_MESSAGES/messages.po', 'locale/de/LC_MESSAGES/messages.mo')
