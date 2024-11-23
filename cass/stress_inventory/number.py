import math

print("Starting script...")  # This should output if the script is running

def round_to_nearest_significant(n):
    if n == 0:
        return 0
    
    # Determine the number of digits in the number
    magnitude = int(math.floor(math.log10(abs(n))))
    
    # Calculate the divisor and multiplier
    factor = 10 ** magnitude
    
    # Round the number to the nearest significant figure
    return round(n / factor) * factor

print(f"Nearest Significant of 249 is {round_to_nearest_significant(249)}")
print(f"Nearest Significant of 350 is {round_to_nearest_significant(350)}")
print(f"Nearest Significant of 598 is {round_to_nearest_significant(598)}")
