import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import os

# Database URL from your environment or hardcoded for the script
DATABASE_URL = "postgresql+asyncpg://admin:admin123@localhost:5432/scada_db" 
# Note: Ensure the host/port matches where you run this script from. 
# If running from host machine against docker, use localhost:5432.
# If running inside docker container, use the service name.

async def fix_enum():
    engine = create_async_engine(DATABASE_URL, echo=True)
    
    async with engine.begin() as conn:
        print("Checking for existing enums...")
        
        # Check if type exists
        result = await conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'alarmseverity';"))
        exists = result.scalar()
        
        if exists:
            print("Enum 'alarmseverity' found. Attempting to patch or drop/recreate isn't safe for data.")
            print("However, the error is usually 'duplicate type'.")
            print("Let's try to verify if we need to do anything.")
            # Usually, SQLModel/SQLAlchemy create_all should handle "if not exists", but sometimes fails with Enums.
            # We can try to manually create it if it doesn't exist, OR 
            # if the error is failing on 'COMMIT', it might be a transaction issue.
        else:
            print("Enum 'alarmseverity' NOT found.")

    await engine.dispose()

async def reset_schema():
    """
    WARNING: DESTRUCTIVE. Dropping the type explicitly can solve the 'create_all' conflict.
    Use this if you are in development and can afford to lose data or if you know what you are doing.
    """
    engine = create_async_engine(DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        try:
            # We drop the type with CASCADE to remove columns using it (Data Loss on those columns!)
            # Or we just let SQLAlchemy try again.
            # The error 'typname_1' suggests it's trying to query it.
            
            # Let's try to just print info first.
            pass
        except Exception as e:
            print(e)
            
    await engine.dispose()

if __name__ == "__main__":
    # For this specific error, it often happens when the ENUM is created with one schema/metadata
    # and then accessed with another.
    # The traceback indicates 'sqlalchemy.engine.Engine ... typname_1 ...' which is an introspection query.
    
    # A common fix for "asyncpg + sqlalchemy enum creation":
    # Ensure the Enum is not modifying the schema on every run.
    
    print("This script is a placeholder. The error usually resolves by restarting the DB container if it's a metadata cache desync.")
    print("Or, if 'alarmseverity' was created with a different set of values.")
    
    asyncio.run(fix_enum())
