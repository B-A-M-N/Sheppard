import subprocess
import sys
import os
import shutil
import time
import pwd
import grp
from pathlib import Path

def run_command(command):
    """Execute a shell command and return its output"""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    output, error = process.communicate()
    if process.returncode != 0:
        print(f"Error executing command: {command}")
        print(error.decode())
        return False
    return output.decode().strip()

def setup_project_permissions():
    """Set up project directory permissions"""
    print("\nSetting up project permissions...")
    
    # Get current user and group
    user = os.getenv('SUDO_USER', os.getenv('USER'))
    if not user:
        print("Could not determine current user")
        return False

    try:
        user_info = pwd.getpwnam(user)
        group_info = grp.getgrgid(user_info.pw_gid)
        
        # Get project root directory (parent of current script)
        project_root = os.path.dirname(os.path.abspath(__file__))
        
        # Set ownership and permissions for entire project directory
        run_command(f"sudo chown -R {user}:{group_info.gr_name} {project_root}")
        run_command(f"sudo chmod -R 755 {project_root}")
        print(f"✓ Set permissions for project directory: {project_root}")
        
        # Create required directories if they don't exist
        required_dirs = [
            "data",
            "data/conversations",
            "data/chroma_persistence",
            "data/embeddings",
            "data/stats",
            "data/tools",
            "data/memory",
            "logs",
            "data/memory/episodic",
            "data/memory/semantic",
            "data/memory/contextual",
            "data/memory/general",
            "data/memory/abstracted"
        ]
        
        for dir_path in required_dirs:
            full_path = os.path.join(project_root, dir_path)
            Path(full_path).mkdir(parents=True, exist_ok=True)
            print(f"✓ Verified directory exists: {dir_path}")
            
        return True
        
    except Exception as e:
        print(f"Error setting up project permissions: {e}")
        return False

def database_exists(db_name):
    """Check if database exists"""
    result = run_command(f"sudo -u postgres -i psql -tAc \"SELECT 1 FROM pg_database WHERE datname='{db_name}'\"")
    return result == "1"

def user_exists(username):
    """Check if PostgreSQL user exists"""
    result = run_command(f"sudo -u postgres -i psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='{username}';\"")
    return result == "1"

def install_packages():
    """Install required system packages"""
    print("\nInstalling necessary packages...")
    run_command("sudo apt update")
    run_command("sudo apt install -y redis-server postgresql")

def cleanup_redis():
    """Clean up existing Redis instances"""
    print("\nCleaning up existing Redis instances...")
    redis_dbs = ['ephemeral', 'contextual', 'episodic', 'semantic', 'abstracted']
    
    for i, db_name in enumerate(redis_dbs):
        port = 6370 + i
        service_name = f"redis-{port}.service"
        
        # Stop and disable the service if it exists
        run_command(f"sudo systemctl stop {service_name}")
        run_command(f"sudo systemctl disable {service_name}")
        
        # Remove service file
        if os.path.exists(f"/etc/systemd/system/{service_name}"):
            run_command(f"sudo rm /etc/systemd/system/{service_name}")

        # Remove config file
        config_file = f"/etc/redis/redis-{port}.conf"
        if os.path.exists(config_file):
            run_command(f"sudo rm {config_file}")

        # Clean up data directory
        data_dir = f"/var/lib/redis/{port}"
        if os.path.exists(data_dir):
            run_command(f"sudo rm -rf {data_dir}")

    # Reload systemd
    run_command("sudo systemctl daemon-reload")

def setup_redis():
    """Set up Redis instances"""
    print("\nSetting up Redis...")
    cleanup_redis()
    
    redis_dbs = ['ephemeral', 'contextual', 'episodic', 'semantic', 'abstracted']
    redis_user = "redis"
    
    # Ensure Redis user exists
    try:
        pwd.getpwnam(redis_user)
    except KeyError:
        run_command(f"sudo useradd --system --group --no-create-home {redis_user}")
    
    for i, db_name in enumerate(redis_dbs):
        port = 6370 + i
        
        # Create data directory with proper permissions
        data_dir = f"/var/lib/redis/{port}"
        run_command(f"sudo mkdir -p {data_dir}")
        run_command(f"sudo chown {redis_user}:{redis_user} {data_dir}")
        run_command(f"sudo chmod 750 {data_dir}")
        
        # Create config file
        config_file = f"/etc/redis/redis-{port}.conf"
        config_content = f"""
        port {port}
        dir {data_dir}
        maxmemory 100mb
        maxmemory-policy allkeys-lru
        
        save 60 1
        save 30 10
        save 15 10000
        appendonly yes
        appendfilename "appendonly.aof"
        
        protected-mode no
        bind 127.0.0.1 10.9.66.198
        """
        
        with open("temp_redis.conf", "w") as f:
            f.write(config_content)
        run_command(f"sudo mv temp_redis.conf {config_file}")
        run_command(f"sudo chown {redis_user}:{redis_user} {config_file}")
        run_command(f"sudo chmod 644 {config_file}")
        
        # Create systemd service
        service_content = f"""[Unit]
Description=Redis In-Memory Data Store ({db_name}) on port {port}
After=network.target

[Service]
Type=notify
ExecStart=/usr/bin/redis-server {config_file} --supervised systemd
ExecStop=/usr/bin/redis-cli -p {port} shutdown
TimeoutStartSec=600
TimeoutStopSec=300
Restart=always
User={redis_user}
Group={redis_user}

[Install]
WantedBy=multi-user.target
"""
        
        service_file = f"/etc/systemd/system/redis-{port}.service"
        with open("temp_redis.service", "w") as f:
            f.write(service_content)
        run_command(f"sudo mv temp_redis.service {service_file}")
        run_command(f"sudo chmod 644 {service_file}")
        
        # Start and enable service
        run_command("sudo systemctl daemon-reload")
        run_command(f"sudo systemctl enable redis-{port}.service")
        run_command(f"sudo systemctl start redis-{port}.service")
        
        print(f"✓ Configured Redis instance: {db_name} (port {port})")
        time.sleep(2)  # Wait for service to start

def setup_postgresql():
    """Set up PostgreSQL databases and user"""
    print("\nSetting up PostgreSQL...")
    
    # Enable and start PostgreSQL
    run_command("sudo systemctl enable postgresql")
    run_command("sudo systemctl start postgresql")
    
    # Create or update user
    if not user_exists("sheppard"):
        print("Creating PostgreSQL user 'sheppard'...")
        run_command("sudo -u postgres -i psql -c \"CREATE USER sheppard WITH SUPERUSER PASSWORD '1234';\"")
    else:
        print("User 'sheppard' already exists, updating permissions...")
        run_command("sudo -u postgres -i psql -c \"ALTER USER sheppard WITH SUPERUSER;\"")
    
    # Create and configure databases
    databases = ["episodic_memory", "semantic_memory", "contextual_memory", 
                "general_memory", "abstracted_memory"]
    
    for db in databases:
        if not database_exists(db):
            print(f"Creating database: {db}")
            run_command(f"sudo -u postgres -i psql -c 'CREATE DATABASE {db};'")
        else:
            print(f"Database '{db}' already exists, updating permissions...")
        
        # Ensure proper permissions
        run_command(f"sudo -u postgres -i psql -c 'GRANT ALL PRIVILEGES ON DATABASE {db} TO sheppard;'")
        
        # Set up permissions within each database
        privileges_commands = [
            f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO sheppard;",
            f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO sheppard;",
            f"GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO sheppard;",
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO sheppard;",
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO sheppard;",
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO sheppard;"
        ]
        
        for cmd in privileges_commands:
            run_command(f"sudo -u postgres -i psql -d {db} -c '{cmd}'")
        
        print(f"✓ Configured database: {db}")
    
    print("✓ PostgreSQL setup completed")

def verify_installation():
    """Verify the complete installation"""
    print("\nVerifying installation...")
    
    # Check Redis services
    redis_ok = True
    for i in range(5):
        port = 6370 + i
        service_status = run_command(f"systemctl is-active redis-{port}.service")
        if service_status != "active":
            redis_ok = False
            print(f"✗ Redis service on port {port} is not running")
        else:
            print(f"✓ Redis service on port {port} is running")
    
    # Check PostgreSQL
    pg_ok = run_command("systemctl is-active postgresql") == "active"
    if pg_ok:
        print("✓ PostgreSQL service is running")
    else:
        print("✗ PostgreSQL service is not running")
    
    # Verify PostgreSQL connection
    try:
        test_cmd = "PGPASSWORD='1234' psql -h localhost -U sheppard -d episodic_memory -c '\\q'"
        pg_conn_ok = run_command(test_cmd) is not False
        if pg_conn_ok:
            print("✓ PostgreSQL connection test successful")
        else:
            print("✗ PostgreSQL connection test failed")
    except Exception as e:
        print(f"✗ PostgreSQL connection test failed: {e}")
        pg_conn_ok = False
    
    if redis_ok and pg_ok and pg_conn_ok:
        print("\n✓ All components verified successfully!")
        return True
    else:
        print("\n✗ Verification failed. Please check the errors above.")
        return False

def main():
    try:
        # Set up project permissions first
        if not setup_project_permissions():
            print("\n✗ Project permissions setup failed")
            return
        
        # Install and configure services
        install_packages()
        setup_redis()
        setup_postgresql()
        
        # Clean up any temporary files
        if os.path.exists("temp_redis.conf"):
            os.remove("temp_redis.conf")
        if os.path.exists("temp_redis.service"):
            os.remove("temp_redis.service")
        
        # Verify installation
        if verify_installation():
            print("\nSetup completed successfully!")
            print("You can now run the main application.")
        else:
            print("\nSetup completed with errors. Please resolve the issues before running the application.")
            
    except Exception as e:
        print(f"\n✗ Error during setup: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("This script must be run as root (sudo)")
        sys.exit(1)
    main()
