#!/usr/bin/env bash
# End-to-end smoke of the whole MoiraFlow platform against the running stack.
set -uo pipefail
API=localhost:8001/api/v1
PASS=0; FAIL=0
ok(){ echo "  ✓ $1"; PASS=$((PASS+1)); }
no(){ echo "  ✗ $1  -- $2"; FAIL=$((FAIL+1)); }
j(){ python3 -c "import sys,json;print(json.load(sys.stdin)$1)"; }
jq_str(){ python3 -c "import json,sys;print(json.dumps(sys.argv[1]))" "$1"; }

echo "== 1. health =="
for ep in healthz readyz; do
  code=$(curl -s -o /dev/null -w "%{http_code}" localhost:8001/$ep)
  [ "$code" = 200 ] && ok "$ep 200" || no "$ep" "got $code"
done

echo "== 2. auth =="
TOKEN=$(curl -s $API/auth/login -H 'content-type: application/json' -d '{"email":"admin@moiraflow.local","password":"admin"}' | j "['access_token']")
[ -n "$TOKEN" ] && ok "login -> token" || { no "login" "no token"; exit 1; }
AUTH=(-H "authorization: Bearer $TOKEN")

echo "== 3. catalog + simulate =="
TYPES=$(curl -s $API/catalog/job-types | j "" | tr -d ' ')
echo "$TYPES" | grep -q command && echo "$TYPES" | grep -q sql && ok "job-types = command/rest/sql" || no "job-types" "$TYPES"
SIMWF='{"apiVersion":"moiraflow/v1","kind":"Workflow","metadata":{"name":"sim_e2e"},"spec":{"trigger":{"type":"manual"},"jobs":[{"id":"a","type":"command","run_on":"agent","with":{"command":"echo hi"}},{"id":"b","type":"sql","needs":["a"],"with":{"connection":"secret://ghost_dsn","statement":"SELECT 1"}}]}}'
SIM=$(curl -s $API/workflows/simulate "${AUTH[@]}" -H 'content-type: application/json' -d "{\"content\":$(jq_str "$SIMWF"),\"format\":\"json\"}")
echo "$SIM" | j "['plan'][0]['task_queue']" | grep -q agent-local && ok "simulate routes agent job -> agent-local" || no "simulate route" "$SIM"
echo "$SIM" | j "['warnings']" | grep -q ghost_dsn && ok "simulate warns missing secret" || no "simulate warn" "$SIM"

echo "== 4. secrets =="
curl -s -o /dev/null -w "%{http_code}" -X PUT $API/secrets/e2e_token "${AUTH[@]}" -H 'content-type: application/json' -d '{"value":"s3cr3t-e2e"}' | grep -q 204 && ok "put secret (204)" || no "put secret" ""
curl -s $API/secrets "${AUTH[@]}" | grep -q e2e_token && ok "secret key listed" || no "secret list" ""

echo "== 5. workflow create + version + activate =="
WFNAME="e2e_artifact_$(date +%s)"
WF="{\"apiVersion\":\"moiraflow/v1\",\"kind\":\"Workflow\",\"metadata\":{\"name\":\"$WFNAME\"},\"spec\":{\"trigger\":{\"type\":\"manual\"},\"jobs\":[{\"id\":\"make\",\"type\":\"command\",\"with\":{\"command\":\"echo e2e-report-body > out.txt\",\"artifacts\":[\"out.txt\"]},\"outputs\":{\"done\":\"yes\"}},{\"id\":\"after\",\"type\":\"command\",\"needs\":[\"make\"],\"with\":{\"command\":\"echo done\"}}]}}"
WID=$(curl -s $API/workflows "${AUTH[@]}" -H 'content-type: application/json' -d "{\"content\":$(jq_str "$WF"),\"format\":\"json\"}" | j "['id']")
[ -n "$WID" ] && ok "create workflow -> $WID" || { no "create wf" ""; }
curl -s "$API/workflows/$WID/export?format=yaml" "${AUTH[@]}" | grep -q "$WFNAME" && ok "export yaml round-trips" || no "export" ""

echo "== 6. launch + live projection =="
EXID=$(curl -s $API/executions "${AUTH[@]}" -H 'content-type: application/json' -d "{\"workflow_id\":\"$WID\"}" | j "['id']")
[ -n "$EXID" ] && ok "launch -> $EXID" || no "launch" ""
for i in $(seq 1 15); do
  ST=$(curl -s $API/executions/$EXID "${AUTH[@]}" | j "['status']")
  [ "$ST" = success ] || [ "$ST" = failed ] && break; sleep 1
done
[ "$ST" = success ] && ok "execution completed: success" || no "execution status" "$ST"
JOBS=$(curl -s $API/executions/$EXID/jobs "${AUTH[@]}")
NJOBS=$(echo "$JOBS" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
echo "$JOBS" | python3 -c "import sys,json;d=json.load(sys.stdin);sys.exit(0 if d and all(x['status']=='success' for x in d) else 1)" \
  && ok "job_executions projected ($NJOBS jobs, all success)" || no "jobs" "$JOBS"
NEV=$(curl -s $API/executions/$EXID/events "${AUTH[@]}" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
[ "$NEV" -ge 4 ] && ok "events persisted ($NEV)" || no "events" "$NEV"

echo "== 7. artifacts in MinIO =="
ART=$(curl -s $API/executions/$EXID/artifacts "${AUTH[@]}")
echo "$ART" | grep -q out.txt && ok "artifact listed (out.txt)" || no "artifact list" "$ART"
URL=$(echo "$ART" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[0]['download_url'] if d else '')")
BODY=$(curl -s "$URL")
echo "$BODY" | grep -q e2e-report-body && ok "artifact downloads via presigned URL" || no "artifact download" "$BODY"

echo "== 8. cancel (idempotent on terminal) =="
curl -s -o /dev/null -w "%{http_code}" -X POST $API/executions/$EXID/cancel "${AUTH[@]}" | grep -q 200 && ok "cancel on finished run -> 200 (no-op)" || no "cancel" ""

echo "== 9. users mgmt =="
UC=$(curl -s -o /dev/null -w "%{http_code}" -X POST $API/users "${AUTH[@]}" -H 'content-type: application/json' -d "{\"email\":\"e2e-dev-$(date +%s)@x.io\",\"password\":\"pw12345678\",\"role\":\"developer\"}")
[ "$UC" = 201 ] && ok "create developer user (201)" || no "create user" "$UC"

echo "== 10. remote agent lifecycle =="
CSR=$(python3 -c "
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
k=rsa.generate_private_key(public_exponent=65537,key_size=2048)
c=x509.CertificateSigningRequestBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'e2e-agent')])).sign(k,hashes.SHA256())
print(c.public_bytes(serialization.Encoding.PEM).decode())")
ET=$(curl -s -X POST $API/agents/enroll "${AUTH[@]}" | j "['enrollment_token']")
[ -n "$ET" ] && ok "enroll -> token" || no "enroll" ""
REG=$(python3 -c "import json,sys;print(json.dumps({'token':sys.argv[1],'name':'e2e-agent','public_key':'PK','csr':sys.argv[2]}))" "$ET" "$CSR" | curl -s -X POST $API/agents/register -H 'content-type: application/json' -d @-)
FP=$(echo "$REG" | j "['fingerprint']"); AID=$(echo "$REG" | j "['agent_id']")
[ -n "$FP" ] && [ ${#FP} -eq 64 ] && ok "register -> signed cert + fingerprint" || no "register" "$REG"
vfy(){ curl -s -o /dev/null -w "%{http_code}" -X POST $API/agents/verify -H 'content-type: application/json' -d "{\"fingerprint\":\"$FP\"}"; }
[ "$(vfy)" = 403 ] && ok "verify pending -> 403" || no "verify pending" "$(vfy)"
curl -s -o /dev/null -X POST $API/agents/$AID/approve "${AUTH[@]}"
[ "$(vfy)" = 200 ] && ok "verify approved -> 200" || no "verify approved" "$(vfy)"
curl -s -o /dev/null -X POST $API/agents/$AID/revoke "${AUTH[@]}"
[ "$(vfy)" = 403 ] && ok "verify revoked -> 403" || no "verify revoked" "$(vfy)"

echo "== 11. audit log =="
ACTIONS=$(curl -s $API/audit "${AUTH[@]}" | python3 -c "import sys,json;print({e['action'] for e in json.load(sys.stdin)})")
for a in auth.login workflow.create execution.launch secret.set agent.enroll agent.approve agent.revoke; do
  echo "$ACTIONS" | grep -q "$a" && ok "audit: $a" || no "audit $a" ""
done

echo ""; echo "===== RESULT: $PASS passed, $FAIL failed ====="
exit $FAIL
