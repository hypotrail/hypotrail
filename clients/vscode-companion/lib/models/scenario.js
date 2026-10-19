'use strict';
// ScenarioModel (WP-B5): the teaching scenario's defaults of the case, read from the full
// view (`status --json`, `view.scenario_defaults`, CLI-CONTRACT §4 and WP-B3, remark R6) for
// the What if? tab. Only `capacity_share` exists: the share of the scored rows a teaching
// case assumes the team can act on. It is an assumption of the exercise, never a figure
// of a team; the panel labels it so and never adopts it. Nothing else of the view is kept.
//
// Keys: revision, capacityShare ({value, status, source} or null).

const { ModelError, str, strOrNull, obj, num, expectSchema, plain } = require('./common');

const SCHEMA = 'hypotrail.status/1';

function toScenarioModel(payload) {
  const p = expectSchema(payload, SCHEMA);
  if (!Number.isInteger(p.revision)) throw new ModelError(`The CLI did not return a ${SCHEMA} document.`);
  const defaults = obj(obj(p.view).scenario_defaults);
  const share = obj(defaults.capacity_share);
  const value = num(share.value);
  return plain({
    revision: p.revision,
    capacityShare: value !== null && value > 0 && value <= 1
      ? { value, status: str(share.status), source: strOrNull(share.source) } : null,
  });
}

const FIXTURES = ['captured/status.shoppers'];

module.exports = { toScenarioModel, FIXTURES, SCHEMA };
