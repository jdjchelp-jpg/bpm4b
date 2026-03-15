import os
import subprocess
import time

def test_mp3_to_m4b():
    print("[*] Testing MP3 to M4B...")
    # Create a dummy MP3 for metadata testing (this won't actually convert audio without a real MP3)
    # We use a real file if available in the source
    input_file = "node_source/test.mp3"
    if not os.path.exists(input_file):
        print("[-] Skipping MP3 test - no test data")
        return
        
    output_file = "test_output.m4b"
    try:
        import sys
        cmd = [sys.executable, "-m", "bpm4b.cli", "convert", input_file, output_file, "--chapter", "Intro", "0", "--chapter", "Part 1", "5"]
        subprocess.run(cmd, check=True)
        if os.path.exists(output_file):
            print("✓ MP3 to M4B Success")
            os.remove(output_file)
        else:
            print("✗ MP3 to M4B Failed - No output")
    except Exception as e:
        print(f"✗ MP3 to M4B Error: {e}")

def main():
    test_mp3_to_m4b()

if __name__ == "__main__":
    main()
