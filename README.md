# midi-to-disklavier
A Python GUI program that preprocesses a MIDI file so that it can be properly played on a Yamaha Disklavier system, without notes getting stuck or notes being improperly sustained.

## What is MIDI
A MIDI file is a file that contains instructions to play music from one or more instruments, by using commands to turn notes on or off. Contrary to an MP3 or M4A file, a MIDI file does not contain any actual sound, only commands. This means that any modern piano with an appropriately equipped YAMAHA Disklavier system can read a MIDI file and parse the commands inside to play the notes.

## Preprocessing
Pianos with a Disklavier system (hereafter referred to as simply 'player pianos') cannot reproduce the sounds that a MIDI file is 'supposed' to make. Limitations on the player piano's electromechanical systems for raising and lowering piano keys means that MIDI files with certain commands will be played back improperly on the player piano.

For example, if a MIDI file contains an instruction to release a piano key, and then press that piano key after 3 milliseconds, it is highly unlikely that the player piano will be able to actually let that piano key rise completely before the key is pressed again. In reality, that key will probably be kept pressed over the 3 milliseconds, meaning that the sound that is supposed to occur on the key press will not be heard.

A visualization of this problem can be seen below.

```
 MIDI                                                <3 ms gap>
command         |note ON|                       |note OFF||note ON|

What the        ┐                               ┌─────────┐
key's height    │                               │         │
should be       └───────────────────────────────┘         └────────────


                                <Slow piano key rise from electromechanical
                                limitations of the player piano system>
How the piano   ┐                                       ___
actually plays   ╲                                ___ ╱    ╲  
      it          ╲─────────────────────────────╱           ╲──────────
```

To eliminate problems like this from occurring, this program goes through all the commands in a MIDI file and creates a gap between any note release-and-presses.

```
  Before       ┐                               ┌─────────┐
   pre-        │                               │         │
processing     └───────────────────────────────┘         └────────────

                             <Gap created to allow piano key to rise>
   After       ┐                       ┌─────────────────┐
   pre-        │                       │                 │
processing     └───────────────────────┘                 └────────────
```

In the program's GUI, the duration of this gap can be specified. Furthermore, in the case that create a gap shortens a piano note's duration by too much, the minimum length of a piano note can also be specified.