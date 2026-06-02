from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess
import time

class Handler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith(".py"):
            print("\n Cambio detectado, ejecutando scraper...\n")
            subprocess.run(["python", "main.py"])

print(" MODO WATCHER ACTIVADO")

event_handler = Handler()
observer = Observer()
observer.schedule(event_handler, path=".", recursive=True)
observer.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    observer.stop()

observer.join()