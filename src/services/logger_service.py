from datetime import datetime
from typing import List, Dict

class SystemLogBuffer:
    def __init__(self, max_size: int = 50):
        self.max_size = max_size
        self.logs: List[Dict[str, str]] = []
        self.add_log("INFO", "System initialized and ready for live procurement scanning.")

    def add_log(self, level: str, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = {"timestamp": timestamp, "level": level, "message": message}
        self.logs.append(entry)
        if len(self.logs) > self.max_size:
            self.logs.pop(0)

    def get_logs(self, limit: int = 20) -> List[Dict[str, str]]:
        return self.logs[-limit:]

system_logger = SystemLogBuffer()
