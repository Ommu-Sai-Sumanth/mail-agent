from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict
import sqlite3
import hashlib
import json
import time


app = FastAPI()


DB = "agent.db"


# ----------------------------
# Database
# ----------------------------

def db():

    return sqlite3.connect(DB)



def init_db():

    conn = db()
    cur = conn.cursor()


    cur.execute("""
    CREATE TABLE IF NOT EXISTS proposals(
        fingerprint TEXT PRIMARY KEY,
        dossier_id TEXT,
        proposal TEXT
    )
    """)


    cur.execute("""
    CREATE TABLE IF NOT EXISTS evaluations(
        evaluation_id TEXT PRIMARY KEY,
        digest TEXT
    )
    """)


    cur.execute("""
    CREATE TABLE IF NOT EXISTS commits(
        receipt_id TEXT PRIMARY KEY,
        result TEXT
    )
    """)


    conn.commit()
    conn.close()



init_db()



# ----------------------------
# Request schema
# ----------------------------

class AgentRequest(BaseModel):

    model_config = ConfigDict(
        extra="allow"
    )


    operation: str

    evaluationId: str | None = None

    dossiers: list | None = None

    receipts: list | None = None



# ----------------------------
# Helpers
# ----------------------------

def hash_json(data):

    raw = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":")
    )

    return hashlib.sha256(
        raw.encode()
    ).hexdigest()



def create_ai_decision(dossier):

    """
    Replace this function with your AI model call.
    """

    text = str(
        dossier.get(
            "content",
            ""
        )
    ).lower()


    if (
        "ignore previous instructions" in text
        or "system prompt" in text
        or "reveal secret" in text
        or "send credentials" in text
    ):

        return {

            "action":
            "quarantine_item",

            "target":
            None,

            "payload":
            None,

            "evidence":
            [
                "Content attempts to control agent behavior"
            ]

        }



    if (
        "already completed" in text
        or "duplicate" in text
    ):

        return {

            "action":
            "no_action",

            "target":
            None,

            "payload":
            None,

            "evidence":
            [
                "Message indicates duplicate or completed work"
            ]

        }



    return {

        "action":
        "request_confirmation",

        "target":
        "approval_queue",

        "payload":
        {
            "reason":
            "identity or authorization requires confirmation"
        },

        "evidence":
        [
            "Authorization is unclear"
        ]

    }




# ----------------------------
# Endpoint
# ----------------------------

@app.post("/")
async def agent(req: AgentRequest):


    # ==========================
    # PROPOSE
    # ==========================

    if req.operation == "propose":


        if req.evaluationId is None:

            raise HTTPException(
                400,
                "missing evaluationId"
            )


        if req.dossiers is None:

            raise HTTPException(
                400,
                "missing dossiers"
            )


        # Validate duplicate IDs

        ids = []

        for d in req.dossiers:

            if not isinstance(d, dict):

                raise HTTPException(
                    400,
                    "invalid dossier"
                )


            if "id" not in d:

                raise HTTPException(
                    400,
                    "missing dossier id"
                )


            ids.append(
                d["id"]
            )


        if len(ids) != len(set(ids)):

            raise HTTPException(
                400,
                "duplicate dossier ids"
            )



        conn = db()
        cur = conn.cursor()


        proposals = []



        for dossier in req.dossiers:


            fp = hash_json(
                dossier
            )


            cur.execute(
                """
                SELECT proposal
                FROM proposals
                WHERE fingerprint=?
                """,
                (fp,)
            )


            row = cur.fetchone()



            if row:

                proposal = json.loads(
                    row[0]
                )


            else:


                proposal = create_ai_decision(
                    dossier
                )


                proposal["callId"] = hashlib.sha256(
                    (
                        fp +
                        str(time.time())
                    ).encode()
                ).hexdigest()



                cur.execute(
                    """
                    INSERT INTO proposals
                    VALUES(?,?,?)
                    """,
                    (
                        fp,
                        dossier["id"],
                        json.dumps(proposal)
                    )
                )



            proposals.append(
                proposal
            )



        digest = hash_json(
            proposals
        )


        cur.execute(
            """
            INSERT OR REPLACE INTO evaluations
            VALUES(?,?)
            """,
            (
                req.evaluationId,
                digest
            )
        )


        conn.commit()
        conn.close()



        return {

            "status":
            "awaiting_receipts",

            "proposals":
            proposals

        }



    # ==========================
    # COMMIT
    # ==========================

    if req.operation == "commit":


        if req.receipts is None:

            raise HTTPException(
                400,
                "missing receipts"
            )


        conn = db()
        cur = conn.cursor()


        outcomes = []



        for receipt in req.receipts:


            if not isinstance(receipt, dict):

                raise HTTPException(
                    400,
                    "invalid receipt"
                )


            receipt_id = receipt.get(
                "receiptId"
            )


            if not receipt_id:

                raise HTTPException(
                    400,
                    "missing receipt id"
                )



            cur.execute(
                """
                SELECT result
                FROM commits
                WHERE receipt_id=?
                """,
                (receipt_id,)
            )


            existing = cur.fetchone()



            if existing:

                outcomes.append(
                    json.loads(existing[0])
                )

                continue



            result = {

                "receiptId":
                receipt_id,

                "status":
                "accepted"

            }


            cur.execute(
                """
                INSERT INTO commits
                VALUES(?,?)
                """,
                (
                    receipt_id,
                    json.dumps(result)
                )
            )


            outcomes.append(
                result
            )



        conn.commit()
        conn.close()



        return {

            "status":
            "completed",

            "outcomes":
            outcomes

        }



    raise HTTPException(
        400,
        "invalid operation"
    )
