#!/usr/bin/env python3
"""
Deploy voice memory system to servo skull Pi 5.
"""
import os
import sys
import subprocess
import tempfile

SERVO_SKULL_IP = "100.69.9.99"
SSH_KEY = "/root/.ssh/id_ed25519"
DEPLOY_PATH = "/home/omni/voice-memory-system"

def run_ssh_command(command, capture_output=True):
    """Run command on servo skull via SSH"""
    ssh_cmd = [
        "ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no",
        f"omni@{SERVO_SKULL_IP}", command
    ]
    
    if capture_output:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    else:
        return subprocess.run(ssh_cmd).returncode == 0

def deploy_voice_memory_system():
    """Deploy voice memory system to servo skull"""
    print(f"🚀 Deploying voice memory system to servo skull at {SERVO_SKULL_IP}...")
    
    # Test SSH connectivity
    print("1. Testing SSH connectivity...")
    success, output, error = run_ssh_command("whoami")
    if not success:
        print(f"❌ SSH connection failed: {error}")
        return False
    
    print(f"✅ SSH connected as: {output.strip()}")
    
    # Create deployment directory
    print("2. Creating deployment directory...")
    success, _, error = run_ssh_command(f"mkdir -p {DEPLOY_PATH}")
    if not success:
        print(f"❌ Failed to create directory: {error}")
        return False
    
    # Copy voice memory system files
    print("3. Copying voice memory system files...")
    files_to_copy = [
        "session_manager.py",
        "layered_memory.py", 
        "context_builder.py",
        "websocket_context.py",
        "__init__.py"
    ]
    
    for file in files_to_copy:
        if os.path.exists(file):
            scp_cmd = [
                "scp", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no",
                file, f"omni@{SERVO_SKULL_IP}:{DEPLOY_PATH}/"
            ]
            result = subprocess.run(scp_cmd, capture_output=True)
            if result.returncode != 0:
                print(f"❌ Failed to copy {file}")
                return False
            print(f"✅ Copied {file}")
        else:
            print(f"⚠️  Warning: {file} not found")
    
    # Test Python import
    print("4. Testing Python imports on servo skull...")
    test_command = f"cd {DEPLOY_PATH} && python3 -c 'from session_manager import SessionManager; print(\"Import successful\")'"
    success, output, error = run_ssh_command(test_command)
    
    if success:
        print(f"✅ Python imports working: {output.strip()}")
    else:
        print(f"❌ Import test failed: {error}")
        return False
    
    print("🎉 Voice memory system deployed successfully!")
    return True

if __name__ == "__main__":
    success = deploy_voice_memory_system()
    sys.exit(0 if success else 1)
