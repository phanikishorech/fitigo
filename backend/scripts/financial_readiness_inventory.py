"""Explicit read-only database inventory; no workers, migrations or financial writes."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-read-only',action='store_true',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    output=Path(args.output)
    if not output.is_absolute():parser.error('Output must be an absolute path.')
    from app.database.session import engine
    from app.core.config import settings
    from app.services.financial_deployment_readiness import inventory
    result=inventory(engine,settings)
    # Exclusive creation preserves earlier attestations.
    with output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,default=str)
    print('Read-only inventory saved; no database changes:',output)


if __name__=='__main__':main()