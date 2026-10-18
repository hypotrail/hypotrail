// Learn view. WP-0 placeholder: it registers its tab at stage v3 and renders
// "Not available in this stage." so stage gating is testable. Owned by WP-U5
// (COMPANION-ADVANCED §6.6), which replaces the render; see ARCHITECTURE.md.
(function (HT) {
  'use strict';
  HT.register('learn', {
    tab: 'learn',
    stage: 'v3',
    views: [],
    render(model, ctx) {
      return ctx.placeholder();
    },
  });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
