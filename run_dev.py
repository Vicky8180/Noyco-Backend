import uvicorn
import threading
import time
import sys
import os
import argparse
import subprocess
from typing import List, Dict

services: List[Dict] = [
    {"module": "api_gateway.main", "port": 8000, "name": "API Gateway", "app_var": "socket_app"},

    {"module": "core.main", "port": 8002, "name": "Core Service"},
  
    {"module": "memory.main", "port": 8010, "name": "Memory Service", "delay": 2},

    #  Support agents services
    {"module": "specialists.agents.main", "port": 8015, "name": "Agents Specialist"},
]

def run_service(module: str, port: int, name: str, delay: int = 0, app_var: str = "app", reload: bool = False):
    """Run a FastAPI service using uvicorn"""
    time.sleep(delay)  # Add delay if specified
    print(f"Starting {name} on port {port}...")

    if reload:
        # For reload mode, use subprocess to start uvicorn directly
        cmd = [
            sys.executable, "-m", "uvicorn",
            f"{module}:{app_var}",
            "--host", "0.0.0.0",
            "--port", str(port),
            "--log-level", "warning"
        ]
        if reload:
            cmd.append("--reload")

        try:
            # Ensure child process can import top-level packages from Noyco-Backend
            base_dir = os.path.dirname(os.path.abspath(__file__))
            env = os.environ.copy()
            env["PYTHONPATH"] = base_dir + (os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else "")
            process = subprocess.Popen(cmd, cwd=base_dir, env=env)
            return process  # Return the process object
        except Exception as e:
            print(f"Error starting {name}: {str(e)}", file=sys.stderr)
            return None
    else:
        # For non-reload mode, use the original approach
        try:
            uvicorn.run(
                app=f"{module}:{app_var}",
                host="0.0.0.0",
                port=port,
                log_level="warning",
                reload=False,
                workers=1
            )
        except Exception as e:
            print(f"Error in {name}: {str(e)}", file=sys.stderr)
            sys.exit(1)

def start_all_services(dev_mode: bool = False):
    """Start all services in separate threads or subprocesses"""
    processes = []
    threads = []

    for service in services:
        if dev_mode:
            # In dev mode, start as separate processes
            time.sleep(service.get("delay", 0))
            process = run_service(
                service["module"],
                service["port"],
                service["name"],
                app_var=service.get("app_var", "app"),
                reload=True
            )
            if process:
                processes.append((process, service))
        else:
            # In production mode, start as threads
            thread = threading.Thread(
                target=run_service,
                args=(service["module"], service["port"], service["name"]),
                kwargs={
                    "delay": service.get("delay", 0),
                    "app_var": service.get("app_var", "app"),
                    "reload": False
                },
                daemon=True
            )
            thread.start()
            threads.append(thread)
            time.sleep(0.5)

    return processes if dev_mode else threads

if __name__ == "__main__":
    # Normalize working directory and Python path so module imports resolve
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    try:
        os.chdir(BASE_DIR)
    except Exception:
        pass
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
    parser = argparse.ArgumentParser(description='Run all Medical AI services')
    parser.add_argument('mode', nargs='?', default='', help='Use "dev" for development mode with hot reload')
    args = parser.parse_args()

    dev_mode = args.mode.lower() == 'dev'

    print(f"Starting Medical AI Services in {'development' if dev_mode else 'production'} mode...")

    if dev_mode:
        processes = start_all_services(dev_mode=True)

        try:
            # Monitoring loop for processes
            while True:
                time.sleep(5)
                for i, (process, service) in enumerate(processes):
                    if process.poll() is not None:  # Process has terminated
                        print(f"Critical: {service['name']} has stopped", file=sys.stderr)
                        # Restart crashed service
                        new_process = run_service(
                            service["module"],
                            service["port"],
                            service["name"],
                            app_var=service.get("app_var", "app"),
                            reload=True
                        )
                        if new_process:
                            processes[i] = (new_process, service)
        except KeyboardInterrupt:
            print("\nShutting down all services...")
            for process, _ in processes:
                try:
                    process.terminate()
                except:
                    pass
            sys.exit(0)
    else:
        threads = start_all_services(dev_mode=False)

        try:
            # Monitoring loop for threads
            while True:
                time.sleep(5)
                for i, thread in enumerate(threads):
                    if not thread.is_alive():
                        print(f"Critical: {services[i]['name']} has stopped", file=sys.stderr)
                        # Restart crashed service
                        new_thread = threading.Thread(
                            target=run_service,
                            args=(services[i]["module"], services[i]["port"], services[i]["name"]),
                            kwargs={
                                "delay": services[i].get("delay", 0),
                                "app_var": services[i].get("app_var", "app"),
                                "reload": False
                            },
                            daemon=True
                        )
                        new_thread.start()
                        threads[i] = new_thread
        except KeyboardInterrupt:
            print("\nShutting down all services...")
            sys.exit(0)