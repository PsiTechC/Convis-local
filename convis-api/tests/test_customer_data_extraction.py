"""
Unit tests for customer data extraction utility
Tests the extract_customer_data function with various inputs
"""
import pytest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.customer_data_extraction import extract_customer_data, format_customer_data_display


class TestNameExtraction:
    """Test name extraction with various patterns"""

    def test_basic_name_extraction(self):
        """Test basic 'my name is' pattern"""
        transcript = "Hi, my name is John Smith and I'd like help."
        result = extract_customer_data(transcript)
        assert result.get("name") == "John Smith"

    def test_lowercase_name(self):
        """Test case-insensitive name extraction"""
        transcript = "my name is praveen"
        result = extract_customer_data(transcript)
        assert result.get("name") == "Praveen"

    def test_uppercase_name(self):
        """Test uppercase name gets title cased"""
        transcript = "MY NAME IS JOHN SMITH"
        result = extract_customer_data(transcript)
        assert result.get("name") == "John Smith"

    def test_name_with_this_is_pattern(self):
        """Test 'this is' calling pattern"""
        transcript = "Hello, this is Sarah Johnson calling about my account"
        result = extract_customer_data(transcript)
        assert result.get("name") == "Sarah Johnson"

    def test_call_me_pattern(self):
        """Test 'call me' pattern"""
        transcript = "You can call me Robert"
        result = extract_customer_data(transcript)
        assert result.get("name") == "Robert"

    def test_name_stops_at_and(self):
        """Test name extraction stops at 'and'"""
        transcript = "my name is John Smith and I live in LA"
        result = extract_customer_data(transcript)
        assert result.get("name") == "John Smith"
        assert "And" not in result.get("name", "")

    def test_no_false_positive_assistant(self):
        """Test rejection of 'assistant' in name"""
        transcript = "Your friendly assistant from Company"
        result = extract_customer_data(transcript)
        assert "name" not in result

    def test_no_false_positive_service(self):
        """Test rejection of 'service' in name"""
        transcript = "The customer service team will help"
        result = extract_customer_data(transcript)
        assert "name" not in result

    def test_name_with_numbers_rejected(self):
        """Test names with numbers are rejected"""
        transcript = "my name is John123"
        result = extract_customer_data(transcript)
        assert "name" not in result

    def test_single_letter_name_rejected(self):
        """Test single letter names are rejected"""
        transcript = "my name is A"
        result = extract_customer_data(transcript)
        assert "name" not in result

    def test_very_long_name_rejected(self):
        """Test extremely long names are rejected"""
        transcript = "my name is " + "A" * 60
        result = extract_customer_data(transcript)
        assert "name" not in result


class TestEmailExtraction:
    """Test email extraction with various patterns"""

    def test_basic_email(self):
        """Test basic email extraction"""
        transcript = "You can reach me at john.smith@example.com"
        result = extract_customer_data(transcript)
        assert result.get("email") == "john.smith@example.com"

    def test_email_with_numbers(self):
        """Test email with numbers"""
        transcript = "My email is user123@company.org"
        result = extract_customer_data(transcript)
        assert result.get("email") == "user123@company.org"

    def test_email_with_plus(self):
        """Test email with plus sign"""
        transcript = "Contact me at john+test@example.com"
        result = extract_customer_data(transcript)
        assert result.get("email") == "john+test@example.com"

    def test_email_various_tlds(self):
        """Test various valid TLDs"""
        valid_emails = [
            "test@example.com",
            "test@example.org",
            "test@example.net",
            "test@example.edu",
            "test@example.gov",
            "test@example.co",
            "test@example.io",
            "test@example.ai",
        ]
        for email in valid_emails:
            result = extract_customer_data(f"Email: {email}")
            assert result.get("email") == email, f"Failed for {email}"

    def test_email_invalid_tld_rejected(self):
        """Test email with invalid TLD is rejected"""
        transcript = "My email is test@example.xyz"
        result = extract_customer_data(transcript)
        assert "email" not in result

    def test_email_no_at_symbol_rejected(self):
        """Test malformed email is rejected"""
        transcript = "My email is test.example.com"
        result = extract_customer_data(transcript)
        assert "email" not in result


class TestLocationExtraction:
    """Test location extraction with various patterns"""

    def test_im_from_pattern(self):
        """Test 'I'm from' pattern"""
        transcript = "I'm from New York"
        result = extract_customer_data(transcript)
        assert result.get("location") == "New York"

    def test_calling_from_pattern(self):
        """Test 'calling from' pattern"""
        transcript = "I'm calling from Los Angeles, CA"
        result = extract_customer_data(transcript)
        assert "Los Angeles" in result.get("location", "")

    def test_live_in_pattern(self):
        """Test 'I live in' pattern"""
        transcript = "I live in Chicago"
        result = extract_customer_data(transcript)
        assert result.get("location") == "Chicago"

    def test_my_address_pattern(self):
        """Test 'my address is' pattern"""
        transcript = "my address is 123 Main Street"
        result = extract_customer_data(transcript)
        assert "123 Main Street" in result.get("location", "")

    def test_location_too_short_rejected(self):
        """Test very short locations are rejected"""
        transcript = "I'm from NY"
        result = extract_customer_data(transcript)
        # NY is too short (less than 3 chars)
        assert "location" not in result or len(result.get("location", "")) >= 3

    def test_generic_location_rejected(self):
        """Test generic words are rejected"""
        generic_words = ["here", "there", "home", "work", "office"]
        for word in generic_words:
            transcript = f"I'm from {word}"
            result = extract_customer_data(transcript)
            assert "location" not in result, f"Should reject '{word}'"


class TestAppointmentExtraction:
    """Test appointment extraction with various patterns"""

    def test_appointment_with_day_and_time(self):
        """Test appointment with day and time"""
        transcript = "I'd like to book an appointment for Monday 15th at 3:00 PM"
        result = extract_customer_data(transcript)
        assert "appointment" in result
        assert "Monday" in result.get("appointment", "")

    def test_appointment_tomorrow(self):
        """Test appointment for tomorrow"""
        transcript = "Can I schedule an appointment for tomorrow at 10 AM?"
        result = extract_customer_data(transcript)
        assert result.get("appointment") == "tomorrow"

    def test_meeting_pattern(self):
        """Test meeting instead of appointment"""
        transcript = "I need a meeting for Tuesday at 2 PM"
        result = extract_customer_data(transcript)
        assert "appointment" in result
        assert "Tuesday" in result.get("appointment", "")

    def test_appointment_without_time(self):
        """Test appointment with just day"""
        transcript = "scheduled for Wednesday"
        result = extract_customer_data(transcript)
        assert "appointment" in result
        # Should still work if it has a day name

    def test_vague_scheduling_rejected(self):
        """Test vague scheduling is rejected"""
        transcript = "I need help scheduling soon"
        result = extract_customer_data(transcript)
        assert "appointment" not in result

    def test_sometime_next_week_rejected(self):
        """Test 'sometime next week' is rejected"""
        transcript = "Can we meet sometime next week"
        result = extract_customer_data(transcript)
        assert "appointment" not in result


class TestCompleteExtraction:
    """Test complete customer data extraction"""

    def test_all_fields_extraction(self):
        """Test extracting all fields at once"""
        transcript = (
            "Hi, my name is Alex Martinez from Los Angeles. "
            "My email is alex@company.com and I need to schedule "
            "a meeting for tomorrow at 2 PM."
        )
        result = extract_customer_data(transcript)

        assert result.get("name") == "Alex Martinez"
        assert result.get("email") == "alex@company.com"
        assert "Los Angeles" in result.get("location", "")
        assert result.get("appointment") == "tomorrow"

    def test_partial_extraction(self):
        """Test extraction with only some fields present"""
        transcript = "My name is Sarah and my email is sarah@test.com"
        result = extract_customer_data(transcript)

        assert result.get("name") == "Sarah"
        assert result.get("email") == "sarah@test.com"
        assert "location" not in result
        assert "appointment" not in result

    def test_empty_transcript(self):
        """Test empty transcript returns empty dict"""
        result = extract_customer_data("")
        assert result == {}

    def test_none_transcript(self):
        """Test None transcript returns empty dict"""
        result = extract_customer_data(None)
        assert result == {}

    def test_no_customer_data(self):
        """Test transcript with no extractable data"""
        transcript = "The weather is nice today"
        result = extract_customer_data(transcript)
        assert result == {}


class TestFormatCustomerDataDisplay:
    """Test the display formatting function"""

    def test_format_all_fields(self):
        """Test formatting with all fields"""
        customer_data = {
            "name": "John Smith",
            "location": "New York",
            "email": "john@example.com",
            "appointment": "Monday at 3 PM"
        }
        result = format_customer_data_display(customer_data)

        assert "👤 John Smith" in result
        assert "📍 New York" in result
        assert "📧 john@example.com" in result
        assert "📅 Monday at 3 PM" in result

    def test_format_partial_fields(self):
        """Test formatting with only some fields"""
        customer_data = {
            "name": "Jane Doe",
            "email": "jane@test.com"
        }
        result = format_customer_data_display(customer_data)

        assert "👤 Jane Doe" in result
        assert "📧 jane@test.com" in result
        assert "📍" not in result
        assert "📅" not in result

    def test_format_empty_data(self):
        """Test formatting with empty data"""
        result = format_customer_data_display({})
        assert result == "-"

    def test_format_none_data(self):
        """Test formatting with None"""
        result = format_customer_data_display(None)
        assert result == "-"


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_multiple_names_first_wins(self):
        """Test that first valid name is used"""
        transcript = "My name is Robert Davis and I'm speaking with Assistant Sarah"
        result = extract_customer_data(transcript)
        assert result.get("name") == "Robert Davis"

    def test_case_insensitive_patterns(self):
        """Test patterns work with any case"""
        transcript = "MY NAME IS JOHN and I'M FROM NEW YORK"
        result = extract_customer_data(transcript)
        assert result.get("name") == "John"

    def test_special_characters_in_context(self):
        """Test extraction works with punctuation"""
        transcript = "Hi! My name is John, and my email is john@test.com."
        result = extract_customer_data(transcript)
        assert result.get("name") == "John"
        assert result.get("email") == "john@test.com"

    def test_very_long_transcript(self):
        """Test extraction from very long transcript"""
        transcript = "A" * 1000 + " my name is Test User " + "B" * 1000
        result = extract_customer_data(transcript)
        assert result.get("name") == "Test User"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
