import multiprocessing
import sys
import tempfile
from io import StringIO
from pathlib import Path
from typing import Dict

from app.tool.base import BaseTool
from app.logger import logger


class PythonExecute(BaseTool):
    """A tool for executing Python code with timeout and safety restrictions."""

    name: str = "python_execute"
    description: str = "Executes Python code string. Note: Only print outputs are visible, function return values are not captured. Use print statements to see results."
    parameters: dict = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The Python code to execute.",
            },
        },
        "required": ["code"],
    }

    def _run_code(self, code: str, result_dict: dict, safe_globals: dict) -> None:
        original_stdout = sys.stdout
        try:
            output_buffer = StringIO()
            sys.stdout = output_buffer
            exec(code, safe_globals, safe_globals)
            result_dict["observation"] = output_buffer.getvalue()
            result_dict["success"] = True
        except Exception as e:
            result_dict["observation"] = str(e)
            result_dict["success"] = False
        finally:
            sys.stdout = original_stdout

    def _execute_in_current_env(
        self,
        code: str,
        timeout: int = 5,
    ) -> Dict:
        """
        Executes Python code in the current environment using multiprocessing.

        Args:
            code (str): The Python code to execute.
            timeout (int): Execution timeout in seconds.

        Returns:
            Dict: Contains 'observation' with execution output and 'success' status.
        """
        with multiprocessing.Manager() as manager:
            result = manager.dict({"observation": "", "success": False})
            if isinstance(__builtins__, dict):
                safe_globals = {"__builtins__": __builtins__}
            else:
                safe_globals = {"__builtins__": __builtins__.__dict__.copy()}
            proc = multiprocessing.Process(
                target=self._run_code, args=(code, result, safe_globals)
            )
            proc.start()
            proc.join(timeout)

            # timeout process
            if proc.is_alive():
                proc.terminate()
                proc.join(1)
                return {
                    "observation": f"Execution timeout after {timeout} seconds",
                    "success": False,
                }
            return dict(result)

    async def _execute_in_sandbox(
        self,
        code: str,
        timeout: int = 5,
    ) -> Dict:
        """
        Executes Python code in the sandbox environment.

        Args:
            code (str): The Python code to execute.
            timeout (int): Execution timeout in seconds.

        Returns:
            Dict: Contains 'observation' with execution output and 'success' status.
        """
        try:
            from app.sandbox.client import SANDBOX_CLIENT

            # Ensure sandbox is initialized
            await SANDBOX_CLIENT.create()

            # Create a temporary file to store the Python code
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False
            ) as f:
                temp_script = f.name
                f.write(code)

            # Copy the script to sandbox
            container_script_path = f"/workspace/{Path(temp_script).name}"
            await SANDBOX_CLIENT.copy_to(temp_script, container_script_path)

            # Execute the Python script in sandbox
            command = f"python {container_script_path}"
            output = await SANDBOX_CLIENT.run_command(command, timeout)

            # Clean up temporary file
            Path(temp_script).unlink(missing_ok=True)

            return {
                "observation": output,
                "success": True,
            }
        except Exception as e:
            logger.error(f"Error executing code in sandbox: {e}")
            return {
                "observation": f"Sandbox execution error: {str(e)}",
                "success": False,
            }

    async def execute(
        self,
        code: str,
        timeout: int = 5,
    ) -> Dict:
        """
        Executes the provided Python code with a timeout.

        Execution location is determined by config.sandbox.use_sandbox:
        - If True: Code runs in sandbox environment
        - If False: Code runs in current environment

        Args:
            code (str): The Python code to execute.
            timeout (int): Execution timeout in seconds.

        Returns:
            Dict: Contains 'observation' with execution output and 'success' status.
        """
        try:
            from app.config import config

            use_sandbox = config.sandbox.use_sandbox
        except Exception as e:
            logger.warning(
                f"Failed to read sandbox config, defaulting to False: {e}"
            )
            use_sandbox = False

        if use_sandbox:
            logger.debug("Executing Python code in sandbox environment")
            return await self._execute_in_sandbox(code, timeout)
        else:
            logger.debug("Executing Python code in current environment")
            return self._execute_in_current_env(code, timeout)
