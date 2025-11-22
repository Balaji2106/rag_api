import subprocess
import os
from dotenv import load_dotenv

def run_redteam():
    load_dotenv()

    env = os.environ.copy()

    CONFIG = "promptfoo/config/promptfoo.yaml"
    cmd = ["promptfoo", "eval", "-c", CONFIG]

    subprocess.run(cmd, check=True, env=env)

if __name__ == "__main__":
    print("▶ Running Promptfoo Red-Team Evaluation using Azure OpenAI...")
    run_redteam()
    print("✔ Evaluation Complete. Check /ops/promptfoo/results/")
