import argparse
import os
import subprocess
import sys

from agent.pipeline import Pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Reply as Vikash, in Vikash's cloned voice (all cloud, all free)."
    )
    parser.add_argument("text", nargs="?", help="text prompt to answer")
    parser.add_argument("--audio", "-a", help="audio file to transcribe and answer")
    parser.add_argument("--out", "-o", default=None, help="output audio path")
    parser.add_argument("--config", "-c", default="config.yaml", help="config file")
    parser.add_argument(
        "--enroll",
        nargs="?",
        const="voice/ref.wav",
        metavar="AUDIO",
        help="create your voice clone in the cloud from a reference clip",
    )
    parser.add_argument(
        "--name", default="Vikash", help="voice name used with --enroll"
    )
    parser.add_argument("--no-play", action="store_true", help="do not play the output")
    parser.add_argument(
        "--condense-profile",
        action="store_true",
        help="summarize profile.md into profile_summary.md (saves prompt tokens)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.config):
        parser.error(f"config not found: {args.config} (run from the Vik_Agent folder)")

    pipeline = Pipeline(args.config)

    if args.condense_profile:
        dst = pipeline.ensure_profile_summary(force=True)
        if dst:
            print(f"Profile summary written: {dst}")
        else:
            print("Nothing to condense (no profile.md, or profile_mode is 'full').")
        return

    if args.enroll:
        voice_id = pipeline.enroll(name=args.name, audio=args.enroll)
        print(f"Voice created. reference_id = {voice_id}")
        print("Saved to voice/voice_id.txt")
        return

    if not args.text and not args.audio:
        parser.error("provide text, --audio, --enroll, or --condense-profile")

    heard, reply, out = pipeline.run(text=args.text, audio=args.audio, out=args.out)

    if heard:
        print(f"Heard : {heard}")
    print(f"Reply : {reply}")
    print(f"Audio : {out}")

    if not args.no_play:
        player = "afplay" if sys.platform == "darwin" else "aplay"
        subprocess.run([player, out], check=False)


if __name__ == "__main__":
    main()
