"""
Customer Data Extraction Utility
Extracts customer information (name, email, phone, appointment) from call transcripts
"""
import re
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def extract_customer_data(transcript: Optional[str]) -> Dict[str, str]:
    """
    Extract customer information from call transcript with high accuracy.
    Only extracts data when confident it's correct.

    Args:
        transcript: Call transcript text

    Returns:
        Dictionary with customer data (name, email, location, appointment)
    """
    if not transcript:
        return {}
    
    # Limit transcript length to prevent performance issues with very long transcripts
    # Process first 5000 characters for extraction (most important info is usually at the start)
    # For very long transcripts, also check the middle section where names often appear
    if len(transcript) > 5000:
        # Extract from first 5000 chars (most common case)
        transcript_to_process = transcript[:5000]
        # Also try middle section (500-5500) in case name appears there
        if len(transcript) > 1000:
            middle_start = len(transcript) // 2 - 500
            middle_end = len(transcript) // 2 + 500
            middle_section = transcript[max(0, middle_start):min(len(transcript), middle_end)]
            # Combine sections for processing
            transcript_to_process = transcript_to_process + " " + middle_section
    else:
        transcript_to_process = transcript

    customer_data = {}

    # Extract name - only with explicit indicators
    # Must have clear context like "my name is", "I am", etc.
    name_patterns = [
        # "my name is John Smith" - match name words (letters only, no adjacent numbers)
        r"(?:my name is|my name's)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)(?:\s|$|[,.\n])",
        r"(?:this is|I am|I'm)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)\s+(?:calling|speaking|here)",  # "this is John calling"
        r"(?:you can call me|call me)\s+([A-Za-z]+)(?:\s|$|[,.\n])",  # "call me John"
    ]
    
    # Words that should NOT be part of a name (stop words)
    stop_words = ['and', 'from', 'in', 'at', 'with', 'for', 'to', 'the', 'a', 'an', 
                  'is', 'are', 'was', 'were', 'be', 'been', 'my', 'your', 'his', 'her',
                  'about', 'who', 'which', 'that', 'this', 'i', 'you', 'we', 'they']
    
    for pattern in name_patterns:
        match = re.search(pattern, transcript_to_process, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            
            # Split name into words and filter out stop words from the end
            name_words = name.split()
            while name_words and name_words[-1].lower() in stop_words:
                name_words.pop()
            
            # Also filter stop words from the beginning (shouldn't happen, but safety)
            while name_words and name_words[0].lower() in stop_words:
                name_words.pop(0)
            
            if not name_words:
                continue
                
            name = ' '.join(name_words)
            
            # Validate: name should be 2-50 chars, not contain numbers
            if 2 <= len(name) <= 50 and not re.search(r'\d', name):
                # Exclude common false positives
                excluded_words = ['assistant', 'customer', 'service', 'support', 'help', 'calling', 'here', 'speaking']
                if not any(word in name.lower() for word in excluded_words):
                    # Capitalize name properly (title case)
                    customer_data["name"] = name.title()
                    break

    # Extract email - try multiple methods

    # Method 1: Standard email format
    email_pattern = r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,}\b'
    email_match = re.search(email_pattern, transcript_to_process)
    if email_match:
        email = email_match.group(0)
        # Additional validation: must have common TLD and reasonable format
        valid_tlds = ['com', 'org', 'net', 'edu', 'gov', 'co', 'io', 'ai', 'app', 'dev', 'in', 'uk', 'us']
        if any(email.lower().endswith('.' + tld) for tld in valid_tlds):
            customer_data["email"] = email

    # Method 2: Try to extract spoken email (if Method 1 didn't find anything)
    if "email" not in customer_data:
        # Look for patterns like "my email is..." or "email address is..."
        # IMPORTANT: Must be followed by something that looks like an email (username + domain)
        spoken_email_patterns = [
            # Pattern requires: word chars, then @ variant, then domain-like text ending with TLD
            r"(?:my email|my email address|email address|email id|email is|mail id is|mail is)[:\s]+([a-zA-Z0-9._-]+\s*(?:at the rate|at sign|@|at)\s*(?:gmail|yahoo|hotmail|outlook|rediffmail|proton|mail)\s*(?:dot|\.)\s*(?:com|co\.in|in|org|net))",
            r"(?:it's|its|it is)[:\s]+([a-zA-Z0-9._-]+\s*(?:at the rate|at sign|@|at)\s*(?:gmail|yahoo|hotmail|outlook|rediffmail|proton|mail)\s*(?:dot|\.)\s*(?:com|co\.in|in|org|net))",
            r"(?:send it to|mail to|email to)[:\s]+([a-zA-Z0-9._-]+\s*(?:at the rate|at sign|@|at)\s*(?:gmail|yahoo|hotmail|outlook|rediffmail|proton|mail)\s*(?:dot|\.)\s*(?:com|co\.in|in|org|net))",
        ]

        for pattern in spoken_email_patterns:
            match = re.search(pattern, transcript_to_process, re.IGNORECASE)
            if match:
                spoken_email = match.group(1).strip()
                # Normalize the spoken email
                normalized = normalize_spoken_email(spoken_email)
                # Validate the normalized email - must have valid structure
                if '@' in normalized and '.' in normalized.split('@')[-1]:
                    # Additional validation: check email length and format
                    if len(normalized) >= 6 and len(normalized) <= 100:
                        # Check if it looks like a real email (has valid chars)
                        if re.match(r'^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', normalized):
                            customer_data["email"] = normalized
                            logger.info(f"[CUSTOMER_DATA] Extracted spoken email: '{spoken_email}' -> '{normalized}'")
                            break

    # Method 3: Look for letter-by-letter spelling with common domains
    if "email" not in customer_data:
        # Pattern for spelled out emails like "J O H N at gmail dot com"
        spelled_pattern = r"([A-Za-z0-9]\s*)+\s*(?:at the rate|at sign|@|at)\s*(?:gmail|yahoo|hotmail|outlook|rediffmail|proton)\s*(?:dot|\.)\s*(?:com|co\.in|in|org|net)"
        match = re.search(spelled_pattern, transcript_to_process, re.IGNORECASE)
        if match:
            spelled_email = match.group(0)
            # Remove spaces between letters but keep structure
            normalized = normalize_spoken_email(spelled_email)
            if '@' in normalized and '.' in normalized:
                customer_data["email"] = normalized
                logger.info(f"[CUSTOMER_DATA] Extracted spelled email: '{spelled_email}' -> '{normalized}'")

    # Extract location - only with explicit context
    location_patterns = [
        r"(?:I'm from|I'm in|I'm calling from|I'm located in|I live in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:,\s*[A-Z]{2,})?)",
        r"\s+from\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*(?:\.|,|and|$)",  # "from New York", "from Los Angeles"
        r"(?:calling from|located in|live in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*(?:\.|,|and|$)",
        r"(?:my (?:address|location) is)\s+(.+?)(?:\.|,|and|$)",
    ]
    for pattern in location_patterns:
        match = re.search(pattern, transcript_to_process, re.IGNORECASE)
        if match:
            location = match.group(1).strip()
            # Clean up location - remove trailing words like "about", "and", etc.
            location = re.sub(r'\s+(?:about|and|or|the|a|an)$', '', location, flags=re.IGNORECASE)
            # Validate: reasonable length, not too generic
            if 3 <= len(location) <= 100:
                # Exclude generic words that might be false positives
                excluded = ['here', 'there', 'home', 'work', 'office', 'calling', 'speaking']
                if not any(word in location.lower() for word in excluded):
                    customer_data["location"] = location.strip()
                    break

    # Extract appointment - only with clear date/time context
    appointment_patterns = [
        # "I need a meeting for Tuesday at 2 PM"
        r"(?:I need|I want|I'd like)\s+(?:a\s+)?(?:appointment|meeting|booking)\s+for\s+((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|tomorrow|today)(?:\s+at\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)?)",
        # "appointment on Monday 15th at 3:00 PM"
        r"(?:appointment|meeting|booking|scheduled|reservation)\s+(?:on|for|at)\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+at\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)?)",
        # "scheduled for tomorrow at 2 PM"
        r"(?:appointment|meeting|booking|scheduled|reservation)\s+(?:for|on)\s+(tomorrow|today|next\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))(?:\s+at\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)?",
        # "scheduled for Wednesday" (without time)
        r"(?:appointment|meeting|booking|scheduled|reservation)\s+(?:for|on)\s+((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|tomorrow|today))",
        # "on Monday at 3 PM"
        r"(?:on|for)\s+((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+at\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)?)",
    ]
    for pattern in appointment_patterns:
        match = re.search(pattern, transcript_to_process, re.IGNORECASE)
        if match:
            appointment = match.group(1).strip()
            # Validate: must contain either a day name or time
            days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'tomorrow', 'today']
            has_day = any(day in appointment.lower() for day in days)
            has_time = re.search(r'\d{1,2}:\d{2}', appointment)
            
            if has_day or has_time:
                customer_data["appointment"] = appointment
                break

    logger.debug(f"[CUSTOMER_DATA] Extracted data: {customer_data}")
    return customer_data


def normalize_spoken_email(spoken_email: str) -> str:
    """
    Normalize a spoken email address to standard format.
    Handles common ASR mistakes like:
    - "at the rate" -> "@"
    - "at sign" -> "@"
    - "dot" -> "."
    - "gmail dot com" -> "gmail.com"
    - Extra spaces
    - Common domain misspellings

    Args:
        spoken_email: Email as transcribed by ASR

    Returns:
        Normalized email address
    """
    if not spoken_email:
        return ""

    email = spoken_email.lower().strip()

    # Handle @ symbol variations
    at_patterns = [
        r'\s*at\s*the\s*rate\s*',
        r'\s*at\s*sign\s*',
        r'\s*at\s*rate\s*',
        r'\s*@\s*',
        r'\s+at\s+(?=\w)',  # "at" when followed by a word (like gmail)
    ]
    for pattern in at_patterns:
        email = re.sub(pattern, '@', email, flags=re.IGNORECASE)

    # Handle dot variations
    dot_patterns = [
        r'\s*dot\s*',
        r'\s*period\s*',
        r'\s*point\s*',
    ]
    for pattern in dot_patterns:
        email = re.sub(pattern, '.', email, flags=re.IGNORECASE)

    # Fix common domain misspellings (order matters - check longer strings first)
    domain_corrections = [
        ('yahooo', 'yahoo'),  # Must be before 'yaho'
        ('gmael', 'gmail'),
        ('gmial', 'gmail'),
        ('gmal', 'gmail'),
        ('g mail', 'gmail'),
        ('yaho', 'yahoo'),
        ('outlouk', 'outlook'),
        ('outlok', 'outlook'),
        ('hotmial', 'hotmail'),
        ('hotmal', 'hotmail'),
    ]
    for wrong, correct in domain_corrections:
        if wrong in email:
            email = email.replace(wrong, correct)

    # Fix common TLD misspellings
    tld_corrections = {
        '.comm': '.com',
        '.cpm': '.com',
        '.con': '.com',
        '.ocm': '.com',
        '.orgg': '.org',
        '.nett': '.net',
    }
    for wrong, correct in tld_corrections.items():
        if email.endswith(wrong):
            email = email[:-len(wrong)] + correct

    # Remove all remaining spaces
    email = email.replace(' ', '')

    # Ensure there's exactly one @ symbol
    at_count = email.count('@')
    if at_count > 1:
        # Keep only the first @
        parts = email.split('@')
        email = parts[0] + '@' + ''.join(parts[1:])

    return email


def validate_email_format(email: str) -> Dict[str, any]:
    """
    Validate email format and return detailed results.

    Args:
        email: Email address to validate

    Returns:
        Dictionary with validation results:
        - is_valid: bool - Whether email is valid
        - normalized: str - Normalized email
        - issues: list - List of issues found
        - suggestions: list - Suggested corrections
    """
    result = {
        "is_valid": False,
        "normalized": "",
        "issues": [],
        "suggestions": []
    }

    if not email:
        result["issues"].append("Email is empty")
        return result

    # Normalize first
    normalized = normalize_spoken_email(email)
    result["normalized"] = normalized

    # Check for @ symbol
    if '@' not in normalized:
        result["issues"].append("Missing @ symbol")
        result["suggestions"].append("Please spell out the email including 'at' or '@'")
        return result

    parts = normalized.split('@')
    if len(parts) != 2:
        result["issues"].append("Invalid @ symbol placement")
        return result

    local_part, domain = parts

    # Validate local part
    if not local_part:
        result["issues"].append("Missing username before @")
        return result

    if len(local_part) > 64:
        result["issues"].append("Username too long")
        return result

    # Validate domain
    if not domain:
        result["issues"].append("Missing domain after @")
        return result

    if '.' not in domain:
        result["issues"].append("Domain missing TLD (e.g., .com)")
        result["suggestions"].append("Did you mean @gmail.com or @yahoo.com?")
        return result

    domain_parts = domain.split('.')
    tld = domain_parts[-1]

    # Check TLD
    valid_tlds = ['com', 'org', 'net', 'edu', 'gov', 'co', 'io', 'ai', 'app', 'dev', 'in', 'uk', 'us']
    if tld not in valid_tlds:
        result["issues"].append(f"Unusual TLD: .{tld}")
        if tld in ['comm', 'cpm', 'con']:
            result["suggestions"].append("Did you mean .com?")

    # If we got here with no issues, it's valid
    if not result["issues"]:
        result["is_valid"] = True

    return result


def spell_out_email(email: str) -> str:
    """
    Convert email to phonetic spelling for confirmation.
    Uses NATO phonetic alphabet for clarity.

    Args:
        email: Email address

    Returns:
        Phonetic spelling of email
    """
    nato = {
        'a': 'Alpha', 'b': 'Bravo', 'c': 'Charlie', 'd': 'Delta',
        'e': 'Echo', 'f': 'Foxtrot', 'g': 'Golf', 'h': 'Hotel',
        'i': 'India', 'j': 'Juliet', 'k': 'Kilo', 'l': 'Lima',
        'm': 'Mike', 'n': 'November', 'o': 'Oscar', 'p': 'Papa',
        'q': 'Quebec', 'r': 'Romeo', 's': 'Sierra', 't': 'Tango',
        'u': 'Uniform', 'v': 'Victor', 'w': 'Whiskey', 'x': 'X-ray',
        'y': 'Yankee', 'z': 'Zulu',
        '0': 'Zero', '1': 'One', '2': 'Two', '3': 'Three', '4': 'Four',
        '5': 'Five', '6': 'Six', '7': 'Seven', '8': 'Eight', '9': 'Nine',
        '@': 'at', '.': 'dot', '_': 'underscore', '-': 'dash'
    }

    result = []
    for char in email.lower():
        if char in nato:
            result.append(f"{nato[char]}")
        else:
            result.append(char)

    return " ".join(result)


def format_customer_data_display(customer_data: Optional[Dict[str, str]]) -> str:
    """
    Format customer data for display in UI.

    Args:
        customer_data: Dictionary with customer information

    Returns:
        Formatted string for display
    """
    if not customer_data:
        return "-"

    parts = []

    if customer_data.get("name"):
        parts.append(f"👤 {customer_data['name']}")

    if customer_data.get("location"):
        parts.append(f"📍 {customer_data['location']}")

    if customer_data.get("email"):
        parts.append(f"📧 {customer_data['email']}")

    if customer_data.get("appointment"):
        parts.append(f"📅 {customer_data['appointment']}")

    return " | ".join(parts) if parts else "-"
