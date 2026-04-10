tell application "Notes"
	set noteCount to count of notes
	set maxNotes to noteCount

	repeat with i from 1 to maxNotes
		set n to note i
		set noteName to name of n
		set noteBody to plaintext of n
		set noteDate to creation date of n
		set dateStr to (year of noteDate as string) & "-" & text -2 thru -1 of ("0" & ((month of noteDate as number) as string)) & "-" & text -2 thru -1 of ("0" & (day of noteDate as string)) & "T00:00:00Z"

		-- Output one note per block, separated by a unique delimiter
		log "===NOTE_START==="
		log "NAME:" & noteName
		log "DATE:" & dateStr
		log noteBody
		log "===NOTE_END==="
	end repeat
end tell
