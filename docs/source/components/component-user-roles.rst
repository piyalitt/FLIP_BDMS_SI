.. _rbac-roles:

###########
User Roles
###########

.. list-table::
   :widths: 5 90
   :header-rows: 1

   * - Role
     - Description
   * - ``admin``
     - Grants all platform permissions including; project approval, unstaging projects, deleting any project, managing deployments (deployment mode), managing the site banner, user management, accessing the admin panel, and all ``researcher`` capabilities.
   * - ``researcher``
     - Allows a user to create and manage FLIP projects including; creating projects, managing projects for which they have access, creating cohort queries, staging projects for approval on specified trusts, creating models, uploading files required for a model, and initiating model training.
   * - ``observer``
     - Provides read-only access to assigned projects. Observers can view project details, cohort query results, model metrics and training results, and download model results. Observers cannot create or edit projects, run or save cohort queries, create or edit models, upload model files, or initiate training.

***********
Permissions
***********

The following table summarises the permissions assigned to each role:

.. list-table::
   :widths: 40 10 10 10
   :header-rows: 1

   * - Permission
     - Admin
     - Researcher
     - Observer
   * - Access admin panel
     - Yes
     - No
     - No
   * - Approve projects
     - Yes
     - No
     - No
   * - Unstage projects
     - Yes
     - No
     - No
   * - Delete any project
     - Yes
     - No
     - No
   * - Manage deployments (deployment mode)
     - Yes
     - No
     - No
   * - Manage site banner
     - Yes
     - No
     - No
   * - Manage users
     - Yes
     - No
     - No
   * - Manage projects (create, edit, stage, train)
     - Yes
     - Yes
     - No

.. note::

   Observers have no explicit permissions. Their read-only access to projects is granted through project user access records (i.e., being added to a project by its owner or an admin).
