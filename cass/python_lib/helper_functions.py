import os,time

def box_print(text_to_print):
        # Decide the drawing mode
        term = os.environ.get("TERM", "")
        if term in ["xterm", "xterm-256color", "screen-256color"]:
            horizontal_line = "\u2500"
            vertical_line = "\u2502"
            top_left = "\u250C"
            top_right = "\u2510"
            bottom_left = "\u2514"
            bottom_right = "\u2518"
        else:
            horizontal_line = "-"
            vertical_line = "|"
            top_left = "+"
            top_right = "+"
            bottom_left = "+"
            bottom_right = "+"

        horizontal_line = "-"
        vertical_line = "|"
        top_left = "+"
        top_right = "+"
        bottom_left = "+"
        bottom_right = "+"

        result_length = len(text_to_print)
        print_line = horizontal_line * (result_length+2)
        print(f"{top_left}{print_line}{top_right}")
        print(f"{vertical_line} {text_to_print} {vertical_line}")
        print(f"{bottom_left}{print_line}{bottom_right}")
        time.sleep(1)
