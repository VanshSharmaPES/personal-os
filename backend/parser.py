import re
import datetime


def parse_message(text):
    """
    Parse natural language message and return structured data.

    Args:
        text (str): The input message from user

    Returns:
        dict: Parsed information with type and relevant fields
    """
    text = text.strip()
    text_lower = text.lower()

    # Check for status update keywords first (they're more specific)
    status_keywords = ['rejected', 'offer', 'hired', 'ghosted', 'interview', 'shortlisted']
    for keyword in status_keywords:
        if keyword in text_lower:
            # Extract company - look for patterns like "at X", "from X", or just before the keyword
            company = extract_company_for_status(text, keyword)
            return {
                'type': 'status_update',
                'company': company.title() if company else 'Unknown',
                'status': keyword
            }

    # Check for application patterns
    application_patterns = [
        r'applied\s+to\s+(.+?)\s+for\s+(.+?)(?:\s+(?:role|position|job|internship))?$',
        r'applying\s+to\s+(.+?)\s+for\s+(.+?)(?:\s+(?:role|position|job|internship))?$',
        r'applied\s+for\s+(.+?)\s+at\s+(.+?)(?:\s+(?:role|position|job|internship))?$',
        r'applying\s+for\s+(.+?)\s+at\s+(.+?)(?:\s+(?:role|position|job|internship))?$'
    ]

    for pattern in application_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            company = match.group(1).strip()
            role = match.group(2).strip()
            # Clean up role - remove trailing words like "role", "position" if they weren't caught by the lookahead
            role = re.sub(r'\s+(role|position|job|internship)$', '', role, flags=re.IGNORECASE)
            return {
                'type': 'application',
                'company': company.title(),
                'role': role.title(),
                'notes': text
            }

    # Check for deadline patterns
    deadline_patterns = [
        r'(.+?)\s+due\s+(\d{1,2}[\s/-]\d{1,2}[\s/-]\d{2,4})',
        r'(.+?)\s+due\s+on\s+(\d{1,2}[\s/-]\d{1,2}[\s/-]\d{2,4})',
        r'(.+?)\s+due\s+([A-Za-z]+[\s,]+\d{1,2}[a-z]*[\s,]+\d{2,4})',
        r'(.+?)\s+due\s+on\s+([A-Za-z]+[\s,]+\d{1,2}[a-z]*[\s,]+\d{2,4})'
    ]

    for pattern in deadline_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            title = match.group(1).strip()
            date_str = match.group(2).strip()
            due_date = parse_date(date_str)
            if due_date:
                category = determine_category(title)
                return {
                    'type': 'deadline',
                    'title': title.title(),
                    'due_date': due_date,
                    'category': category
                }

    # Default to unknown
    return {'type': 'unknown'}


def extract_company_for_status(text, keyword):
    """Extract company name from status update text."""
    # Try patterns like "at X", "from X", "at X company", etc.
    patterns = [
        rf'at\s+(.+?)\s+{re.escape(keyword)}',
        rf'from\s+(.+?)\s+{re.escape(keyword)}',
        rf'{re.escape(keyword)}\s+at\s+(.+?)(?:\s|$)',
        rf'{re.escape(keyword)}\s+from\s+(.+?)(?:\s|$)'
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # If no pattern found, try to get text before the keyword
    index = text.lower().find(keyword)
    if index > 0:
        # Get text before keyword, last few words
        before = text[:index].strip()
        words = before.split()
        if len(words) >= 2:
            return ' '.join(words[-2:])  # Last two words
        elif len(words) == 1:
            return words[0]

    return 'Unknown'


def parse_date(date_str):
    """Parse date from various formats."""
    # Remove ordinal indicators like st, nd, rd, th
    date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str, flags=re.IGNORECASE)

    # Try different formats
    formats = [
        '%Y-%m-%d',      # 2026-07-15
        '%d/%m/%Y',      # 15/07/2026
        '%m/%d/%Y',      # 07/15/2026
        '%B %d %Y',      # July 15 2026
        '%d %B %Y',      # 15 July 2026
        '%b %d %Y',      # Jul 15 2026
        '%d %b %Y',      # 15 Jul 2026
    ]

    for fmt in formats:
        try:
            return datetime.datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue

    return None


def determine_category(title):
    """Determine category based on keywords in title."""
    title_lower = title.lower()

    academic_keywords = ['capstone', 'assignment', 'exam', 'submission', 'semester', 'dbms', 'ml', 'se', 'course']
    aiesec_keywords = ['aiesec', 'recruitment', 'lc', 'mc', 'ogta', 'people management']
    internship_keywords = ['internship', 'sanjeevani', 'pesurf']

    for keyword in academic_keywords:
        if keyword in title_lower:
            return 'academic'

    for keyword in aiesec_keywords:
        if keyword in title_lower:
            return 'aiesec'

    for keyword in internship_keywords:
        if keyword in title_lower:
            return 'internship'

    # Default to academic
    return 'academic'


# Test function (can be removed later)
if __name__ == '__main__':
    # Test cases
    test_cases = [
        "Applied to VectorShift for ML Engineer role",
        "Applying to Google for Software Engineer position",
        "Applied for Software Engineer at Microsoft",
        "Applying for Internship at Tesla",
        "Capstone Submission due July 15 2026",
        "Assignment due on 15/07/2026",
        "Exam due June 30th 2026",
        "Project Due on July 4th, 2026",
        "Got rejected from Peakflo",
        "Received offer from Google",
        "Had interview at Microsoft",
        "You were hired by Amazon",
        "Some random message",
        "Apply to Facebook for Data Scientist role tomorrow",
    ]

    for test in test_cases:
        result = parse_message(test)
        print(f"Input: {test}")
        print(f"Output: {result}")
        print("-" * 50)