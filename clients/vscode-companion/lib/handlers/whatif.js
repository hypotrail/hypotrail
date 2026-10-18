'use strict';
// Whatif handler. WP-0 skeleton: it handles nothing yet, so a message of its
// types is ignored and a `load` of its views answers "Not available in this stage.".
// Owned by WP-U3, which adds `load: whatif`, `preview_policy` (debounce, `seq`, cache), `draft`, and `propose` (W3, with the draft re-read just before) (COMPANION-ADVANCED §6.5). The controller discovers
// this module; see lib/controller.js for the {types, loads, onReady} interface.

module.exports = { types: {}, loads: {} };
