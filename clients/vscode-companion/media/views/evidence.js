// Evidence view. WP-0 placeholder: it registers its tab at stage v2 and renders
// "Not available in this stage." so stage gating is testable. Owned by WP-U3
// (COMPANION-ADVANCED §6.4), which replaces the render; see ARCHITECTURE.md.
(function (HT) {
  'use strict';
  HT.register('evidence', {
    tab: 'evidence',
    stage: 'v2',
    views: [],
    render(model, ctx) {
      return ctx.placeholder();
    },
  });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
