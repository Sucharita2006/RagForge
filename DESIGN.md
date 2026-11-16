---
name: ragforge
description: A sign system for a RAG console. Magenta points to where the proof is; ink carries the record; every answer sentence carries its verdict.
colors:
  signal-magenta: "#A3135A"
  signal-magenta-pressed: "#85104A"
  ink: "#111318"
  ink-secondary: "#3A3D44"
  ink-muted: "#5C606A"
  figure-panel: "#16181D"
  concourse-grey: "#F4F5F7"
  card-white: "#FFFFFF"
  track-grey: "#E7E9EE"
  rule-grey: "#D3D6DC"
  verified-green: "#0A7A3D"
  verified-green-on-dark: "#4BD98A"
  refuted-orange: "#C2410C"
  refuted-orange-wash: "#FCE9DF"
typography:
  figure:
    fontFamily: "Fira Sans, system-ui, sans-serif"
    fontSize: "8rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.03em"
    fontFeature: "tnum"
  headline:
    fontFamily: "Fira Sans, system-ui, sans-serif"
    fontSize: "2rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Fira Sans, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 700
    lineHeight: 1.4
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Fira Sans, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.5
  body-small:
    fontFamily: "Fira Sans, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Fira Sans, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.4
  data-mono:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.4
rounded:
  square: "4px"
  control: "6px"
  card: "8px"
  panel: "12px"
spacing:
  gutter: "16px"
  gutter-wide: "24px"
  control-height: "44px"
  section: "48px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.control}"
    height: "44px"
    padding: "0 16px"
  button-primary-hover:
    backgroundColor: "{colors.ink-secondary}"
    textColor: "{colors.card-white}"
  button-secondary:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    height: "44px"
    padding: "0 16px"
  field:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    height: "44px"
    padding: "0 12px"
  nav-band:
    backgroundColor: "{colors.signal-magenta}"
    textColor: "{colors.card-white}"
    height: "56px"
  sign:
    backgroundColor: "{colors.signal-magenta}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.card}"
    padding: "12px 20px 12px 12px"
  sign-hover:
    backgroundColor: "{colors.signal-magenta-pressed}"
  locator-tag:
    backgroundColor: "{colors.signal-magenta}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.square}"
    height: "28px"
    padding: "0 8px 0 4px"
  inset-square:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.square}"
    size: "36px"
  figure-panel:
    backgroundColor: "{colors.figure-panel}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.panel}"
    padding: "24px"
  card:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "16px"
---

# Design System: ragforge

## Overview

**Creative North Star: "The Concourse Sign"**

ragforge is read the way a traveller reads an airport: every screen says where the proof is and which way to go next. One saturated colour, signal magenta, is reserved for that job alone. It fills the navigation band, marks the page you are on, tags each answer sentence with the passage it was checked against, and closes each page with a sign to where the evidence continues. Everything else is ink on a cool grey concourse, so the magenta always reads as direction.

Where one number decides an outcome (an answer's confidence, the abstain threshold, the promotion gate's verdict) it is set at gate-number scale in a near-black figure panel, the way a sign sets the gate it points to. Data stays dense and tabular around it: fixed-cell tables, tabular figures, verdicts drawn as a mark plus a word.

The interface is light only, for a reviewer at a desk reading results for a few minutes.

**Key Characteristics:**
- Signal magenta directs and does nothing else.
- One humanist signage sans, Fira Sans, at every size; monospace only for ids and code.
- Monumental figures in a near-black panel wherever one number decides.
- Numbered and lettered inset squares tie answer sentences to the passages they cite.
- Every page ends on a sign to where its proof continues.

## Colors

A restrained cool-grey field with one committed directional colour and two state colours.

### Primary
- **Signal Magenta** (signal-magenta): the navigation band, the open group, the 3px bar under the current sub-page, locator tags ("↓ Passage A") and next-step signs. Its pressed shade (signal-magenta-pressed) is the hover and active state of every magenta element.

### Secondary
- **Verified Green** (verified-green): a sentence supported by its passage, an improved metric, an active model. On the near-black panel the lighter verified-green-on-dark marks an answered question.
- **Refuted Orange** (refuted-orange): a sentence the passage does not support, a regressed metric, a failed run. Its wash (refuted-orange-wash) is the ground of an error message.

### Neutral
- **Ink** (ink): text, primary buttons, inset squares, table header rules, the whole-request bar in a timeline.
- **Secondary Ink** (ink-secondary): supporting text, inactive sub-page links, primary-button hover.
- **Muted Ink** (ink-muted): captions, placeholders, unscored and neutral verdicts, every step bar in a timeline, the second line of a chart.
- **Figure Panel** (figure-panel): the near-black ground behind monumental figures.
- **Concourse Grey** (concourse-grey): the page.
- **Card White** (card-white): passage cards, empty states, fields, the sub-page row.
- **Track Grey** (track-grey): bar tracks, skeletons, row hover and the selected row.
- **Rule Grey** (rule-grey): hairlines between rows and around regions.

### Named Rules
**The One Direction Rule.** Magenta appears only on something that points somewhere: navigation, the current page marker, a locator tag or a sign. It is never a state, a chart series or a decoration.

**The Mark-and-Word Rule.** Green and orange never carry a state alone. Every verdict is a drawn mark (check, cross or dash in a filled square) plus a word, so it survives greyscale and colour blindness.

**The Withheld Is Not Failed Rule.** A withheld answer and a refused promotion are outcomes, not errors: they take the neutral dash, never refuted orange.

## Typography

**Display Font:** Fira Sans (with system-ui, sans-serif)
**Body Font:** Fira Sans
**Label/Mono Font:** ui-monospace stack, for ids, span names and code only

**Character:** One humanist signage face across the whole interface, from 8rem figures to 14px table heads. Weight and size carry hierarchy; there is no display pairing.

### Hierarchy
- **Figure** (800, 8rem, falling to 5.5rem below 1280px; 1; tabular figures): the one number that decides a page (confidence on Query, the threshold on Trust settings). The gate verdict uses the same weight at 2.75rem because it is a phrase, not a number.
- **Headline** (700, 2rem, 1.25): page titles.
- **Title** (700, 1.25rem): section headings and the asked question.
- **Body** (400, 1.0625rem, 1.5): answer sentences and page purposes, held to 68ch.
- **Body small** (400, 0.9375rem): table cells, notes, sign details.
- **Label** (600, 0.875rem): field labels, table heads, the label half of stacked table rows.

### Named Rules
**The One Face Rule.** Fira Sans is the only typeface for words. Monospace is for things a machine produced (chunk and trace ids, span names, commands), never for flavour.

## Layout

A centred page up to 82.5rem wide with a 16px gutter (24px from 640px). Sections are 48px apart; more space sits above a heading than below it. On Query, Trust settings and Feedback loop the answer row is a 12-column grid: the figure panel takes 4 columns, the content beside it 8.

Tables keep their columns in fixed cells; a state change restyles a row in place and never reflows the grid. Below 768px, tables marked to stack become one block per row: the row's identity first, then each value as label and value. Cells that only make sense wide (difference plots, a duplicated rank) are hidden there. The pipeline stage chain runs horizontally from 1024px and as a vertical list with down arrows below that.

The navigation band is sticky. From 768px it shows the wordmark, three groups and the Query button; below that, a menu button opens the full page list grouped the same way.

## Elevation & Depth

Flat. There are no shadows. Depth comes from three things only: the near-black figure panel against the grey page, white cards and fields one step off the grey, and the 2px ink rule under a table head.

### Named Rules
**The No-Shadow Rule.** Surfaces never cast shadows. A focused passage is lifted with a 2px ink ring and everything unrelated is dimmed to 40% opacity instead.

## Shapes

Small, near-square corners, like enamelled sign panels: 4px on inset squares and locator tags, 6px on buttons and fields, 8px on cards and signs, 12px on figure panels. Controls have 2px ink borders. Icons are drawn on a 24-unit grid with a 2.75 stroke and square ends.

## Components

### Buttons
Plain and heavy; the primary action reads like a sign.
- **Shape:** gently squared (6px), 44px tall (56px for Ask).
- **Primary:** ink with white type. An action that moves you on (Ask, Search, Compare) leads with its arrow in a white inset square.
- **Hover / Focus:** hover lightens to secondary ink; focus is a 3px ink outline offset 2px (white on the magenta band).
- **Secondary:** white with a 2px ink border; hover fills with track grey.
- **Disabled:** 50% opacity, not-allowed cursor.

### Inputs / Fields
- **Style:** white, 2px ink border, 6px corners, 44px tall (56px for the Query question).
- **Focus:** the shared 3px ink outline.
- **Disabled:** track-grey fill.

### Navigation
- **Band:** 56px of signal magenta. Wordmark at left in 800 weight; three groups (Inspect, Measure, Improve) as white text, the open group a white block with magenta text; a white Query button at right.
- **Sub-page row:** white, below the band, listing the open group's pages; the current page sits on a 3px magenta bar.
- **Phones:** the band shows the wordmark, the current page name and a menu button. The menu lists Query as a magenta block, then each group's pages under a small heading.

### Signs
The system's signature. A magenta block with a white inset square holding a magenta arrow, a bold title and a one-line detail. It ends every page that has a subject and points to where that subject's proof continues. It flips in once when it appears (340ms, ease-out; none under reduced motion).

### Locator Tags
Small magenta tags on each answer sentence, "↓ Passage A", that scroll to and focus the cited passage.

### Inset Squares
Ink squares carrying a white number, letter or arrow: sentence numbers, passage letters, stage numbers, the selected-row marker.

### Figure Panels
Near-black panels holding one monumental figure, a bold label, a one-line explanation, and a short list of supporting facts below a hairline.

### Verdict Marks
A 20px filled square (green check, orange cross or grey dash) followed by a word in the matching colour.

## Do's and Don'ts

### Do:
- **Do** keep signal magenta for things that direct: the band, the current-page bar, locator tags and signs.
- **Do** end a page that has a subject with a sign to where its proof continues.
- **Do** set the number that decides a page at figure scale in a near-black panel.
- **Do** draw every state as a mark plus a word.
- **Do** keep tables in fixed cells and let them stack into label-and-value rows on phones.

### Don't:
- **Don't** use magenta for a state, a chart series or emphasis.
- **Don't** add a second accent colour, including for charts. Chart series use ink and muted ink and are told apart by labels and dash patterns.
- **Don't** cast shadows.
- **Don't** colour a withheld answer or a refused promotion as a failure.
- **Don't** use monospace for anything a person wrote.
