# -*- coding: utf-8 -*-
# Copyright: Sterling Dorminey <sterling.dorminey@gmail.com>
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

# import the main window object (mw) from ankiqt
from aqt import mw
# import the "show info" tool from utils.py
from aqt.utils import showInfo
# import all of the Qt GUI library
from aqt.qt import *

from anki.utils import timestampID

import copy
import re
from PyQt4 import QtCore, QtGui

# Global configuration
DeckPrefix = "Incremental - "
MaxEditDistance = 4

# Forms:
# ------
class NewIncrementalDeck(QDialog):
    def __init__(self):
        QDialog.__init__(self, mw)

        self.setWindowTitle("New incremental deck")
        self.resize(400, 300)
        self.verticalLayout = QVBoxLayout(self)

        self.label = QLabel(self)
        self.label.setText("Which field has words in the target language?")

        self.buttonBox = QDialogButtonBox(self)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

        self.list = QListWidget(self)

        self.verticalLayout.addWidget(self.label)
        self.verticalLayout.addWidget(self.list)
        self.verticalLayout.addWidget(self.buttonBox)

        self.connect(self.buttonBox, SIGNAL("accepted()"), self.onAccepted)
        self.connect(self.buttonBox, SIGNAL("rejected()"), self.onRejected)
        self.populateListItems()

        self.show()
    
    def populateListItems(self):
        model = mw.col.models.current()
        self.fields = model['flds']
        fieldNames = [f['name'] for f in self.fields]
        self.list.addItems(fieldNames)

    def createModel(self):
        oldModel = mw.col.models.current().copy()
        oldModel['selectorField'] = self.fields[self.list.currentRow()]
        return oldModel

    def onAccepted(self):
        "Selection is chosen"
        currentDeck = mw.col.decks.current()
        deckName = DeckPrefix + currentDeck['name']

        # Validation:
        # See if the deck already exists
        did = mw.col.decks.id(deckName, False)

        if did is not None:
            showInfo("Deck already exists.")
            return

        # See if we've actually selected something
        if self.list.currentRow() < 0:
            showInfo("Please select something.")
            return

        # Otherwise, create it.
        did = mw.col.decks.id(deckName, True)
        m = self.createModel()
        deck = mw.col.decks.get(did)
        deck['mid'] = m['id']

        # Save deck
        mw.col.decks.save(deck)
        showInfo("Incremental deck \"%s\" created from current deck." % deckName)

        QDialog.accept(self)

    def onRejected(self):
        "Dialog is rejected"
        QDialog.reject(self)

class IncrementalDeckOptions(QDialog):
    def __init__(self):
        QDialog.__init__(self, mw)

        self.setWindowTitle("Incremental deck options")
        self.resize(400, 300)
        self.gridLayout = QGridLayout(self)

        self.maxEditDistanceLabel = QLabel(self)
        self.maxEditDistanceLabel.setText("Max edit distance:")
        self.maxEditDistance = QSpinBox(self)
        self.gridLayout.addWidget(self.maxEditDistanceLabel, 0, 0)
        self.gridLayout.addWidget(self.maxEditDistance, 0, 1)

        self.connect(self.buttonBox, SIGNAL("accepted()"), self.onAccepted)
        self.connect(self.buttonBox, SIGNAL("rejected()"), self.onRejected)

        self.show()

    def onAccepted(self):
        pass

    def onRejected(self):
        pass

def getMasterDeckNotes():
    "Returns all note ids of the master of the current (incremental) deck."
    currentDeck = mw.col.decks.current()
    if currentDeck is None:
        showInfo("You must be on an incremental deck.")
        return

    match =  re.match(DeckPrefix + "(.+)", currentDeck['name'])
    if match is None:
        showInfo("You must be on an incremental deck.")
        return

    deckName = match.group(1)
    ids = mw.col.findNotes("deck:\"%s\"" % deckName)
    if len(ids) == 0:
        showInfo("The master deck does not exist, or is devoid of notes.")
        return

    return ids
    
def getEditDistance(source, target):
    "Return the Levenshtein edit distance between source and target."
    "Taken from http://en.wikibooks.org/wiki/Algorithm_Implementation/Strings/Levenshtein_distance#Python (4th version)"
    # Heuristic: disregard huge targets.
    if abs(len(source) - len(target)) > MaxEditDistance:
        return MaxEditDistance + 1
    # Heuristic: disregard empty taregts.
    if len(target) == 0:
        return MaxEditDistance + 1

    oneago = None
    thisrow = range(1, len(target) + 1) + [0]
    for x in xrange(len(source)):
        twoago, oneago, thisrow = oneago, thisrow, [0] * len(target) + [x + 1]
        for y in xrange(len(target)):
            delcost = oneago[y] + 1
            addcost = thisrow[y - 1] + 1
            subcost = oneago[y - 1] + (source[x] != target[y])
            thisrow[y] = min(delcost, addcost, subcost)
    return thisrow[len(target) - 1]

def getClosestNote(source, targets):
    "Returns the note id with the smallest edit distance from the source."
    # This algorithm should take roughly ~ O(n) time.
    closestTarget = min(targets, key=lambda target: getEditDistance(source, target[0]))
    closestEditDistance = getEditDistance(source, closestTarget[0])
    if closestEditDistance > MaxEditDistance:
        print "No match for %s" % source
        return None
    print "Closest edit distance to %s, at %d, out of %d targets, was %s" % (source, closestEditDistance, len(targets), closestTarget[0])
    return closestTarget[1]

def getNoteSelectors(noteId):
    "Returns an array of possible selectors for the note. A selector is a possible 'name' for the note."
    note = mw.col.getNote(noteId)
    model = mw.col.models.current()
    field = model['selectorField']
    return [s for n in note[field] for s in n.split()]

def copyToIncrementalDeck(noteId):
    "Copies all cards belonging to the note id to the incremental deck."
    cardIds = mw.col.db.list("select id from cards where nid=?", noteId)
    for cardId in cardIds:
        # Create a copy, and copy it to the current deck id.
        card = mw.col.getCard(cardId)
        card.did = mw.col.decks.selected()
        card.id = timestampID(mw.col.db, "cards")
        card.flush()

# Menu actions:
# -------------
def createDeck():
    "Create a new incremental deck."
    dialog = NewIncrementalDeck()
    return

def deckOptions():
    "Incremental deck options."
    dialog = IncrementalDeckOptions()
    return

def addToDeck():
    "Add all cards relevant to the source text (provided in the clipboard) from the master deck to the incremental deck."
    numAdded = 0
    numNotFound = 0
    numAlreadyAdded = 0

    # Get all notes in the master deck.
    masterNotes = getMasterDeckNotes()
    if masterNotes is None:
        return
    # selector -> note ID (multiple selectors for a single note is possible; we'll need a way to break ties.)
    selectors = [(selector, noteId) for noteId in masterNotes for selector in getNoteSelectors(noteId)]

    # Get note ids already added to the incremental deck.
    noteIdsAlreadyInDeck = set(mw.col.db.list("select distinct nid from cards where did=?", mw.col.decks.selected()))

    # Copy source text from clipboard.
    clipboard = QtGui.QApplication.clipboard()
    sourceText = clipboard.text()

    # Find the closest match for each word in the source text, and add the card.
    sourceWords = sourceText.split()
    for word in sourceWords:
        closestNote = getClosestNote(word, selectors)
        if closestNote is not None:
            if closestNote not in noteIdsAlreadyInDeck:
                print "%s => %s" % (word, mw.col.getNote(closestNote).joinedFields())
                copyToIncrementalDeck(closestNote)
                noteIdsAlreadyInDeck.add(closestNote)
                numAdded += 1
            else:
                numAlreadyAdded += 1
        else:
            numNotFound += 1

    showInfo("Source text was: %s\nAdded %d notes, %d were already known and %d were not found." % (sourceText, numAdded, numAlreadyAdded, numNotFound))

# UI definition:
# --------------
# New incremental deck
newDeckAction = QAction("New incremental deck", mw)
mw.connect(newDeckAction, SIGNAL("triggered()"), createDeck)
mw.form.menuTools.addAction(newDeckAction)

# Incremental deck options
deckOptionsAction = QAction("Incremental deck options", mw)
mw.connect(deckOptionsAction, SIGNAL("triggered()"), deckOptions)
mw.form.menuTools.addAction(deckOptions)

# Add to incremental deck
addDeckAction = QAction("Add to incremental deck", mw)
mw.connect(addDeckAction, SIGNAL("triggered()"), addToDeck)
mw.form.menuTools.addAction(addDeckAction)
