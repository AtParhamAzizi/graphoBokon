import csv
import io
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


class DemoTests(unittest.TestCase):
    def test_offline_workflow_runs_without_third_party_packages_or_network(self):
        demo = Path(__file__).resolve().parents[2] / "demo_project"
        script = textwrap.dedent("""
            import runpy
            import sys

            def reject_network(event, arguments):
                if event == "socket.connect":
                    raise AssertionError("The offline demo must not use the network")

            sys.addaudithook(reject_network)
            sys.path.insert(0, sys.argv[1])
            runpy.run_path(sys.argv[2], run_name="__main__")
        """)
        result = subprocess.run(
            [sys.executable, "-B", "-S", "-c", script, str(demo), str(demo / "run_demo.py")],
            cwd=demo,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        rows = list(csv.DictReader(io.StringIO(result.stdout)))
        self.assertEqual(len(rows), 5)
        self.assertEqual(
            {row["name"] for row in rows},
            {"Ada Lovelace", "Grace Hopper", "Katherine Johnson", "Margaret Hamilton", "Mary Jackson"},
        )
        self.assertTrue(all(row["email"].endswith("@example.com") for row in rows))
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
