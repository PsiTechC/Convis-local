import random

def generate_otp() -> str:
    """
    Generate a random 6-digit OTP

    Returns:
        str: 6-digit OTP as a string
    """
    return str(random.randint(100000, 999999))
