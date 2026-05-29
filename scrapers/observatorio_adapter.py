import glob
import os
import pandas as pd

from . import observatorio_democratico


class ObservatorioDemocraticoScraper:

    def __init__(
        self,
        output_dir="output",
        log_dir="logs",
        test_mode=False
    ):
        self.output_dir = output_dir
        self.log_dir = log_dir
        self.test_mode = test_mode

    def run(self):

        # Ejecuta el script original
        observatorio_democratico.main()

        total_valid = 0

        # Buscar todos los CSV generados
        csv_files = glob.glob("*.csv")

        for file in csv_files:

            if "backup" in file.lower():
                continue

            try:
                df = pd.read_csv(file, sep="|")
                total_valid += len(df)

            except Exception:
                pass

        return {
            "source": "observatorio_democratico",
            "status": "OK",
            "total_valid": total_valid,
            "total_discarded": 0
        }