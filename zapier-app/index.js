'use strict';

const authentication = require('./authentication');
const { includeBearer, handleHttpErrors } = require('./utils/middleware');

const newLeadTrigger = require('./triggers/new_lead');
const leadStatusChangedTrigger = require('./triggers/lead_status_changed');
const searchFinishedTrigger = require('./triggers/search_finished');

const createLead = require('./creates/create_lead');
const updateLeadStatus = require('./creates/update_lead_status');
const addLeadTag = require('./creates/add_lead_tag');

// Hidden trigger exported alongside addLeadTag — drives the dynamic
// dropdown of tags on the "Add Tag to Lead" action.
const tagsListTrigger = addLeadTag.tagsList;

const { version } = require('./package.json');
const platformVersion = require('zapier-platform-core').version;

module.exports = {
  version,
  platformVersion,

  authentication,

  beforeRequest: [includeBearer],
  afterResponse: [handleHttpErrors],

  triggers: {
    [newLeadTrigger.key]: newLeadTrigger,
    [leadStatusChangedTrigger.key]: leadStatusChangedTrigger,
    [searchFinishedTrigger.key]: searchFinishedTrigger,
    [tagsListTrigger.key]: tagsListTrigger,
  },

  creates: {
    [createLead.key]: createLead,
    [updateLeadStatus.key]: updateLeadStatus,
    [addLeadTag.key]: addLeadTag,
  },

  searches: {},
  resources: {},
};
