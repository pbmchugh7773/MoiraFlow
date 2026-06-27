import json
from pathlib import Path

from moiraflow_worker.agent_crypto import decrypt_for_agent

FIXTURE = Path(__file__).parent / "fixtures" / "agent_envelope.json"


def test_agent_decrypts_api_produced_envelope():
    """Cross-service compatibility: the worker decrypts an envelope produced by the
    API's encrypt_for_agent (the fixture), proving the formats match exactly."""
    f = json.loads(FIXTURE.read_text())
    assert decrypt_for_agent(f["private_key_pem"], f["envelope"]) == f["plaintext"]
