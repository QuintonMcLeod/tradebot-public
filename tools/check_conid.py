from ib_insync import IB, Contract
import logging

logging.basicConfig(level=logging.INFO)

def check_conid():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        
        c = Contract(conId=106346291)
        details = ib.reqContractDetails(c)
        if details:
            print(f"!!! FOUND !!!")
            print(f"Contract: {details[0].contract}")
            print(f"Long Name: {details[0].longName}")
            print(f"desc: {details[0].contract.description}")
        else:
            print("conId 106346291 not found.")

        # Also check conId 106346292 just in case
        c = Contract(conId=106346292)
        details = ib.reqContractDetails(c)
        if details:
            print(f"!!! FOUND neighbor !!!")
            print(f"Contract: {details[0].contract}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    check_conid()
