"""Entry point — generates data then runs a sample resolution."""
import subprocess, sys

def main():
    #Generate data files if not present
    import os
    if not os.path.exists("data/gazetteer.json"):
        subprocess.run([sys.executable, "generate_data.py"], check=True)
    
    
    from resolver import resolve
    samples = [
        "inyuma ya big pharmacy on RN3, red gate",
        "derrière Kimironko Market",
        "hafi ya Sitasiyo ya Nyabugogo",
        
    ]
    for text in samples:
        r = resolve(text)
        print(f"Input     : {text}")
        print(f"Result    : lat={r['lat']}, lon={r['lon']}, conf={r['confidence']}")
        print(f"Landmark  : {r['matched_landmark']} | escalate={r['escalate']}")
        print()

if __name__ == "__main__":
    main()
