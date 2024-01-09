import logging
import sys
from typing import List
from registrar.utility.enums import LogCode

logger = logging.getLogger(__name__)


class TerminalColors:
    """Colors for terminal outputs
    (makes reading the logs WAY easier)"""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    YELLOW = "\033[93m"
    MAGENTA = "\033[35m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    BackgroundLightYellow = "\033[103m"


class TerminalHelper:
    @staticmethod
    def query_yes_no(question: str, default="yes"):
        """Ask a yes/no question via raw_input() and return their answer.

        "question" is a string that is presented to the user.
        "default" is the presumed answer if the user just hits <Enter>.
                It must be "yes" (the default), "no" or None (meaning
                an answer is required of the user).

        The "answer" return value is True for "yes" or False for "no".
        """
        valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
        if default is None:
            prompt = " [y/n] "
        elif default == "yes":
            prompt = " [Y/n] "
        elif default == "no":
            prompt = " [y/N] "
        else:
            raise ValueError("invalid default answer: '%s'" % default)

        while True:
            logger.info(question + prompt)
            choice = input().lower()
            if default is not None and choice == "":
                return valid[default]
            elif choice in valid:
                return valid[choice]
            else:
                logger.info("Please respond with 'yes' or 'no' " "(or 'y' or 'n').\n")

    @staticmethod
    def query_yes_no_exit(question: str, default="yes"):
        """Ask a yes/no question via raw_input() and return their answer.

        "question" is a string that is presented to the user.
        "default" is the presumed answer if the user just hits <Enter>.
                It must be "yes" (the default), "no" or None (meaning
                an answer is required of the user).

        The "answer" return value is True for "yes" or False for "no".
        """
        valid = {
            "yes": True,
            "y": True,
            "ye": True,
            "no": False,
            "n": False,
            "e": "exit",
        }
        if default is None:
            prompt = " [y/n] "
        elif default == "yes":
            prompt = " [Y/n] "
        elif default == "no":
            prompt = " [y/N] "
        else:
            raise ValueError("invalid default answer: '%s'" % default)

        while True:
            logger.info(question + prompt)
            choice = input().lower()
            if default is not None and choice == "":
                return valid[default]
            elif choice in valid:
                if valid[choice] == "exit":
                    sys.exit()
                return valid[choice]
            else:
                logger.info("Please respond with a valid selection.\n")

    @staticmethod
    def array_as_string(array_to_convert: List[str]) -> str:
        array_as_string = "{}".format("\n".join(map(str, array_to_convert)))
        return array_as_string

    @staticmethod
    def print_conditional(
        print_condition: bool,
        print_statement: str,
        log_severity: LogCode = LogCode.DEFAULT,
    ):
        """This function reduces complexity of debug statements
        in other functions.
        It uses the logger to write the given print_statement to the
        terminal if print_condition is TRUE.

        print_condition: bool -> Prints if print_condition is TRUE

        print_statement: str -> The statement to print

        log_severity: str -> Determines the severity to log at
        """
        # DEBUG:
        if print_condition:
            match log_severity:
                case LogCode.ERROR:
                    logger.error(print_statement)
                case LogCode.WARNING:
                    logger.warning(print_statement)
                case LogCode.INFO:
                    logger.info(print_statement)
                case LogCode.DEBUG:
                    logger.debug(print_statement)
                case _:
                    logger.info(print_statement)

    @staticmethod
    def prompt_for_execution(system_exit_on_terminate: bool, info_to_inspect: str, prompt_title: str) -> bool:
        """Create to reduce code complexity.
        Prompts the user to inspect the given string
        and asks if they wish to proceed.
        If the user responds (y), returns TRUE
        If the user responds (n), either returns FALSE
        or exits the system if system_exit_on_terminate = TRUE"""

        action_description_for_selecting_no = "skip, E = exit"
        if system_exit_on_terminate:
            action_description_for_selecting_no = "exit"

        # Allow the user to inspect the command string
        # and ask if they wish to proceed
        proceed_execution = TerminalHelper.query_yes_no_exit(
            f"""{TerminalColors.OKCYAN}
            =====================================================
            {prompt_title}
            =====================================================
            *** IMPORTANT:  VERIFY THE FOLLOWING LOOKS CORRECT ***

            {info_to_inspect}
            {TerminalColors.FAIL}
            Proceed? (Y = proceed, N = {action_description_for_selecting_no})
            {TerminalColors.ENDC}"""
        )

        # If the user decided to proceed return true.
        # Otherwise, either return false or exit this subroutine.
        if not proceed_execution:
            if system_exit_on_terminate:
                sys.exit()
            return False
        return True

    @staticmethod
    def get_file_line_count(filepath: str) -> int:
        with open(filepath, "r") as file:
            li = file.readlines()
        total_line = len(li)
        return total_line

    @staticmethod
    def print_to_file_conditional(print_condition: bool, filename: str, file_directory: str, file_contents: str):
        """Sometimes logger outputs get insanely huge."""
        if print_condition:
            # Add a slash if the last character isn't one
            if file_directory and file_directory[-1] != "/":
                file_directory += "/"
            # Assemble filepath
            filepath = f"{file_directory}{filename}.txt"
            # Write to file
            logger.info(f"{TerminalColors.MAGENTA}Writing to file " f" {filepath}..." f"{TerminalColors.ENDC}")
            with open(f"{filepath}", "w+") as f:
                f.write(file_contents)
