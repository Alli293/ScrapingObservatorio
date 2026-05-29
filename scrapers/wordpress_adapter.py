from . import observatorio_democratico


class WordPressSiteAdapter:

    SITE_NAME = None

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

        site = next(
            s
            for s in observatorio_democratico.SITES
            if s["name"] == self.SITE_NAME
        )

        observatorio_democratico.procesar_sitio(site)

        return {
            "source": self.SITE_NAME,
            "status": "OK",
            "total_valid": 0,
            "total_discarded": 0
        }      
          