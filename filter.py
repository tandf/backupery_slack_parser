import yaml

class Filter:
    def __init__(self, path) -> None:
        self.path = path
        self._config = None
        self.open()

    def open(self):
        try:
            with open(self.path, "r") as f:
                self._config = yaml.safe_load(f)
        except Exception:
            pass

    def get_chats(self):
        chats = self._config["chats"]
        chats = {c: [str(d) for d in dates] for c, dates in chats.items()}
        return chats

    def get_copy_files(self) -> bool:
        try:
            return bool(self._config["copy-files"])
        except Exception:
            return False
