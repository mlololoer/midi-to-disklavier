from mido import MidiFile
import mido
from tkinter import *
#from tkinter import scrolledtext
from tkinter import messagebox
from tkinter.filedialog import askopenfilename
#Created by Hyun Joon Jeong. Aug 2020
#Updated July 2021
#   Added pedal command offsets
#   Added better logic for solving overlapped notes
#   Tiny note durations are now automatically lengthened
#   Cleaned and refactored code

window = Tk()
window.title("Prepare a MIDI for player piano")
window.geometry('350x320')

fileName = ''
trackNumber = 0

def chooseFile():
    global fileName
    fileName = askopenfilename(filetypes = (("MIDI files","*.mid"),("All files","*.*")))
    print('File path: ' + fileName)
    truncatedName = fileName.split('/')[-1]
    truncatedName = (truncatedName[:30] + '...') if len(truncatedName) > 30 else truncatedName
    fileNameLabel.configure(text=truncatedName)
    trackSelectorSpinbox.config(state='normal')
    trackSelectorSpinbox.delete(0,len(trackSelectorSpinbox.get()))
    trackSelectorSpinbox.insert(0,'0')
    trackSelectorSpinbox.config(state='readonly')
    window.update()
    if (fileName != ''):
        try:
            readMe = MidiFile(fileName)
            trackSelectorSpinbox.config(from_=0,to=(len(readMe.tracks)-1))
            print('Found ' + str(len(readMe.tracks)) + ' tracks in the file.')
        except IOError:
            print('Error while reading the file.')
            messagebox.showinfo('Error','The MIDI file appears to be corrupted.')
            fileName = ''
            fileNameLabel.configure(text='')
    else:
        print('No file selected')
    #selectFileButton.configure(text=fileName.split('/')[-1])

#Given a tick value, find which tempo message (the idx) that tick is under
def findTempoIdx(tick, tempoStream):
    i = 0
    while (i < len(tempoStream) and tempoStream[i]['absTime'] <= tick):
        i += 1
    return i-1

def IntervalFromTicksInTempo(start, end, tempoIdx, TPB, tempoStream):
    return (end-start) * tempoStream[tempoIdx]['msgData'].tempo / TPB / 1000

#Helper function to calculate the time interval from a start and end tick, accounting for tempo changes
#tempo calculation: tempo * ticks / ticks_per_beat / 1000 = time in milliseconds
def IntervalFromTicks(start, end, TPB, tempoStream):
    startTempoIdx = findTempoIdx(start, tempoStream)
    endTempoIdx = findTempoIdx(end, tempoStream)

    interval = 0

    for tempoIdx in range(startTempoIdx, endTempoIdx):
        interval += IntervalFromTicksInTempo(start, tempoStream[tempoIdx+1]['absTime'], tempoIdx, TPB, tempoStream)
        start = tempoStream[tempoIdx+1]['absTime']

    return interval + IntervalFromTicksInTempo(start, end, endTempoIdx, TPB, tempoStream)

#Given a starting tick, a time interval, and a direction, find the tick value that is however many milliseconds away from the start position, in the given direction
def TickFromInterval(start, interval, forward, TPB, tempoStream):
    tempoIdx = findTempoIdx(start, tempoStream)

    if (forward == True): #Go forwards until the time interval has been used up.
        while (tempoIdx < (len(tempoStream) - 1)): #
            thisTempoInterval = IntervalFromTicksInTempo(start, tempoStream[tempoIdx+1]['absTime'], tempoIdx, TPB, tempoStream)
            if (thisTempoInterval > interval):
                break
            start = tempoStream[tempoIdx+1]['absTime']
            interval -= thisTempoInterval
            tempoIdx += 1
        return start + (interval * 1000 * TPB / tempoStream[tempoIdx]['msgData'].tempo)
    else: #Go backwards
        while (tempoIdx > 0):
            thisTempoInterval = IntervalFromTicksInTempo(tempoStream[tempoIdx]['absTime'], start, tempoIdx, TPB, tempoStream)
            if (thisTempoInterval > interval):
                break
            start = tempoStream[tempoIdx]['absTime']
            interval -= thisTempoInterval
            tempoIdx -= 1
        return max(0, start - (interval * 1000 * TPB / tempoStream[tempoIdx]['msgData'].tempo))

#Syntactic sugar for determining on/off messages
def isPressed(msg):
    msg = msg['msgData']
    if (msg.type == 'control_change' and msg.control == 64):
        return msg.value != 0
    else:
        return not(msg.type == 'note_off' or msg.velocity == 0)

def findPrevNote(pressed, idx, msgs):
    if (idx < 0):
        return -1
    idx -= 1
    while (idx >= 0):
        if (pressed == isPressed(msgs[idx])):
            break
        idx -= 1
    return idx

def findNextNote(pressed, idx, msgs):
    if (idx < 0):
        return -1
    idx += 1
    while (idx < len(msgs)):
        if (pressed == isPressed(msgs[idx])):
            break
        idx += 1
    if (idx >= len(msgs)):
        return -1
    else:
        return idx

def execute():
    
    minDelay = delayTextField.get()
    minNoteLength = minNoteLengthTextField.get()
    pedalOffset = pedalOffsetTextField.get()
    minPedalLength = pedalLengthTextField.get()
    if (not fileName):
        messagebox.showinfo('Error','No file has been selected.')
        return 2
    if (not (minDelay.isdigit() and minNoteLength.isdigit() and pedalOffset.isdigit() and minPedalLength.isdigit() and int(minNoteLength) >= 0 and int(minDelay) >= 0 and int(minPedalLength) >= 0 and int(pedalOffset) >= 0)):
        messagebox.showinfo('Error','Check the minimum delays and lengths and try again. They should be non-negative integers.')
        return 1
    try:
        midi = MidiFile(fileName)
    except IOError:
        print('Error while reading the file.')
        messagebox.showinfo('Error','The MIDI file appears to be corrupted.')
    print('Starting operation on track ' + trackSelectorSpinbox.get() + ' with minimum delay = '+minDelay+', minimum note length = '+minNoteLength)
    minDelay = int(minDelay)
    minNoteLength = int(minNoteLength)
    pedalOffset = int(pedalOffset)
    minPedalLength = int(minPedalLength)
    trackNumber = int(trackSelectorSpinbox.get())
    
    instrumentNoteValueOffset = 19 #note value of the lowest note in the instrument's range. For piano, note 19 is A0.
    instrumentRange = 88 #number of distinct MIDI pitches the instrument can play (88 for a standard piano)

    def noteValueToStr(note):
        #A0 starts at 19.
        #Increases/decreases in intervals of 12.
        note -= 19
        pitches = ['A','A#/Bb','B','C','C#/Db','D','D#/Eb','E','F','F#/Gb','G','G#/Ab']
        return (pitches[note % 12] + str(note // 12))


    noteTable = [[] for i in range(instrumentRange)]
    tempoStream = []
    pedalStream = []
    otherStream = []
    
    modifiedCount = 0
    #Although this modifier is only supposed to work on one track at a time, we need to check if there are tempo events in other tracks.
    #Tempos are universal across all tracks, so we search every track for all the tempo messages and collect them into the tempoStream array.
    #We need every tempo change because we need to calculate the timings between notes later on
    for track in range(len(midi.tracks)):
        absoluteTime = 0
        #Every msg (MIDI event) inside each track
        for msg in midi.tracks[track]:
            absoluteTime += msg.time
            if (msg.type == 'set_tempo'):
                tempoStream.append({'msgData':msg,'absTime':absoluteTime,'inTrackToModify': (track == trackNumber) })
    
    #Now we read note events and other events for the track we want to modify. Add absolute time values to each one to make life easier
    absoluteTime = 0
    for msg in midi.tracks[trackNumber]:
        absoluteTime += msg.time
        thisEvent = {'msgData':msg,'absTime':absoluteTime}
        if (msg.type == 'note_on' or msg.type == 'note_off'):
            noteTable[msg.note - instrumentNoteValueOffset].append(thisEvent)
        elif (msg.type == 'control_change' and msg.control == 64):
            pedalStream.append(thisEvent)
        elif (msg.type != 'set_tempo'): #we've already gathered all the set_tempo events previously
            otherStream.append(thisEvent)
            
    #To get a MIDI file to work on the piano, first I need to make it all on one channel, then I need to shorten
    #notes -- especially repeated notes so there is enough time for the key to release before it is re-struck.
    #Running time is... improveable...

    #Step 2. Go through every sequence of noteon/noteoffs for each pitch, and find cases where a noteOn signal is too close to a previous noteOff signal
    for pitchMsgs in noteTable:
        notePressed = False
        idx = 0
        while (idx < len(pitchMsgs)):
            if (not notePressed): #nothing pressed
                if (isPressed(pitchMsgs[idx])):

                    #---   NOT PRESSED -> PRESSED   ---
                    #      check if prev. note is too close
                    notePressed = True
                    #look for a previous on+off 
                    prevOff = findPrevNote(False, idx, pitchMsgs)
                    prevOn = findPrevNote(True, prevOff, pitchMsgs)
                    if (prevOn < 0):
                        idx += 1
                        continue

                    newPrevOffTick = TickFromInterval(pitchMsgs[idx]['absTime'], minDelay, False, midi.ticks_per_beat, tempoStream)
                    if (pitchMsgs[prevOff]['absTime'] > newPrevOffTick): #the gap between the off & on signal is too small, we need to resize it.                            
                        #without a small enough delay, the key may get stuck and the second noteOn event may not trigger.
                        #ASSUME minNoteLength is VERY small. Therefore, it should not affect the note delay gap too much.
                        #we also need to check if moving the off signal will make the previous note too short!
                        if ((pitchMsgs[prevOn]['absTime'] > newPrevOffTick) or (IntervalFromTicks(pitchMsgs[prevOn]['absTime'], newPrevOffTick, midi.ticks_per_beat, tempoStream) < minNoteLength)):
                            #new prevOff shortens the previous note too much, so we just set prevOff's absTime to minNoteLength ms after prevOn
                            pitchMsgs[prevOff]['absTime'] = TickFromInterval(pitchMsgs[prevOn]['absTime'], minNoteLength, True, midi.ticks_per_beat, tempoStream)
                        else:
                            pitchMsgs[prevOff]['absTime'] = newPrevOffTick
                        modifiedCount += 1
                else:

                    #---   NOT PRESSED -> NOT PRESSED   ---
                    #      delete the previous duplicate noteOff signal (if exists)
                    print("Consecutive note OFF at tick "+str(pitchMsgs[idx]['absTime'])+", note value "+str(pitchMsgs[idx]['msgData'].note))
                    prevOff = findPrevNote(False, idx, pitchMsgs)
                    if (prevOff < 0):
                        idx += 1
                        continue

                    pitchMsgs.pop(prevOff)
                    idx -= 1
                    modifiedCount += 1
            else:
                if (isPressed(pitchMsgs[idx])):
                    print("Consecutive note ON at tick "+str(pitchMsgs[idx]['absTime'])+", note value "+str(pitchMsgs[idx]['msgData'].note))
                    #---   PRESSED -> PRESSED   ---
                    #      we need to create a new noteOff signal which is minDelay ms away from the current noteOn (the hanging noteOff will be handled later)
                    prevOn = findPrevNote(True, idx, pitchMsgs)
                    if (prevOn < 0):
                        idx += 1
                        continue
                    #SPECIAL CASE: Two noteon at the same tick
                    if (pitchMsgs[prevOn]['absTime'] == pitchMsgs[idx]['absTime']):
                        #same note, delete the current one and continue
                        pitchMsgs.pop(idx)
                        modifiedCount += 1
                        continue
                    
                    #Need to place a noteOff event to separate these two noteOn events

                    #Method 2: Create a new noteOff here
                    newPrevOffTick = TickFromInterval(pitchMsgs[idx]['absTime'], minDelay, False, midi.ticks_per_beat, tempoStream)
                    if ((pitchMsgs[prevOn]['absTime'] > newPrevOffTick) or (IntervalFromTicks(pitchMsgs[prevOn]['absTime'], newPrevOffTick, midi.ticks_per_beat, tempoStream) < minNoteLength)):
                        #new prevOff shortens the previous note too much, so we just set prevOff's absTime to minNoteLength ms after prevOn
                        #create the new noteOff here
                        msg = {'msgData':mido.Message('note_off', note=pitchMsgs[idx]['msgData'].note), 'absTime': TickFromInterval(pitchMsgs[prevOn]['absTime'], minNoteLength, True, midi.ticks_per_beat, tempoStream)}
                        pitchMsgs.insert(idx, msg)
                    else:
                        msg = {'msgData':mido.Message('note_off', note=pitchMsgs[idx]['msgData'].note), 'absTime': newPrevOffTick}
                        pitchMsgs.insert(idx, msg)
                    idx += 1
                    modifiedCount += 1

                else:
                    #---   PRESSED -> NOT PRESSED   ---
                    #      check if note is shorter than allowed, and increase if possible
                    notePressed = False
                    prevOn = findPrevNote(True, idx, pitchMsgs)
                    if (prevOn < 0):
                        idx += 1
                        continue

                    #Maybe we only need to extend it here, and we don't need to deal with the possible overlap/note delay since it will be dealt with later?
                    if (IntervalFromTicks(pitchMsgs[prevOn]['absTime'], pitchMsgs[idx]['absTime'], midi.ticks_per_beat, tempoStream) < minNoteLength):
                        #the note's current length is below the minimum note length, so find the new location of the noteOff signal.
                        #(if it goes over the next noteOn, we just set the noteOff to be equal to the noteOn time - 1, but this is unlikely since minNoteLength is so small)
                        newOffTick = TickFromInterval(pitchMsgs[prevOn]['absTime'], minNoteLength, True, midi.ticks_per_beat, tempoStream)
                        nextOn = findNextNote(True, idx, pitchMsgs)
                        if (nextOn >= 0 and newOffTick >= pitchMsgs[nextOn]['absTime']):
                            pitchMsgs[idx]['absTime'] = pitchMsgs[nextOn]['absTime']-1
                        else:
                            pitchMsgs[idx]['absTime'] = newOffTick
                        modifiedCount += 1
            idx += 1

    #Step 3: Move pedal ON commands forward by constant.
            
    #Sustain pedal On commands need to be moved forward so they don't capture released notes that are still resonating,
    #and Off commands need to be moved back quite a bit if there's another on command coming, as the pedal movement is
    #much slower than a key so takes more time to release and re-activate.
    #(it appears that just moving the ON commands forwards is sufficient)
    idx = 0
    while (idx < len(pedalStream)):
        if (isPressed(pedalStream[idx])):
            newOnTick = TickFromInterval(pedalStream[idx]['absTime'], pedalOffset, True, midi.ticks_per_beat, tempoStream)
            nextOff = findNextNote(False, idx, pedalStream)
            if (nextOff < 0):
                idx += 1
                continue

            if (pedalStream[nextOff]['absTime'] < newOnTick):
                #if the newOnTick is greater than the off time, then just set the onTick to be nextOff - minPedalLength
                pedalStream[idx]['absTime'] = TickFromInterval(pedalStream[nextOff]['absTime'], minPedalLength, False, midi.ticks_per_beat, tempoStream)
            else:
                pedalStream[idx]['absTime'] = newOnTick
        idx += 1
    
    processedStream = []
    for event in otherStream:
        processedStream.append(event)
    for event in tempoStream:
        if (event['inTrackToModify']):
            processedStream.append(event)
    for event in pedalStream:
        processedStream.append(event)
    #notes must come after control messages
    for pitch in noteTable:
        for event in pitch:
            processedStream.append(event)
    processedStream = sorted(processedStream, key=lambda event: event['absTime'])

    midi.tracks[trackNumber].clear()
    currentTime = 0
    for event in processedStream:
        timeDifference = event['absTime'] - currentTime
        event['msgData'].time = round(timeDifference)
        midi.tracks[trackNumber].append(event['msgData'])
        currentTime = event['absTime']
        #if (event['remark'] != ''):
        #    #put this in the log next time
        #    print(event['remark'])

        
    truncatedName = fileName.split('/')[-1]
    midi.save(truncatedName[:-4]+'_modified.mid')
    messagebox.showinfo('Success','Modified file saved as ' + truncatedName[:-4]+'_modified.mid' + '. ' + str(modifiedCount) + ' events changed.')


selectFileLabel = Label(window, text='Select a MIDI file: ',padx=10,pady=10)
selectFileLabel.grid(column = 0, row=0)

selectFileButton = Button(window, text='Choose file', command=chooseFile)
selectFileButton.grid(column=1,row=0)

fileNameLabel = Label(window,text='', padx=10,pady=10)
fileNameLabel.grid(column = 0, row = 1)

trackSelectLabel = Label(window,text='Select Track Number', padx = 10,pady=10)
trackSelectLabel.grid(column=0,row=2)

trackSelectorSpinbox = Spinbox(window,width=3,state='readonly')
trackSelectorSpinbox.grid(column=1,row=2)

selectDelayLabel = Label(window, text='Min. delay between note release and press (in ms): ',wraplength = 250,padx=10,pady=10)
selectDelayLabel.grid(column = 0, row=3)

delayTextField = Entry(window, width=10)
delayTextField.grid(column = 1, row=3)

selectMinNoteLengthLabel = Label(window, text='Min. length of any note (in ms): ',wraplength = 250,padx=10,pady=10)
selectMinNoteLengthLabel.grid(column = 0, row=4)

minNoteLengthTextField = Entry(window, width=10)
minNoteLengthTextField.grid(column = 1, row=4)

selectPedalOffsetLabel = Label(window, text='Pedal down command offset (in ms): ',wraplength = 250,padx=10,pady=10)
selectPedalOffsetLabel.grid(column = 0, row=5)

pedalOffsetTextField = Entry(window, width=10)
pedalOffsetTextField.grid(column = 1, row=5)

pedalLengthLabel = Label(window, text='Min. length of any pedal command (in ms): ',wraplength = 250,padx=10,pady=10)
pedalLengthLabel.grid(column = 0, row=6)

pedalLengthTextField = Entry(window, width=10)
pedalLengthTextField.grid(column = 1, row=6)

runButton = Button(window, text='Process MIDI', command=execute)
runButton.grid(column=1,row=7)

logView = scrolledtext.ScrolledText(window, width=30, height=12)
logView.configure(state='disabled')
logView.grid(row=7)

window.mainloop()
