"use client";

// Notifications: the signed-in user's in-app notifications, and for organization-wide administrators the email
// delivery outbox of the selected project's organization. Which sections appear follows the permissions the API
// reports in GET /me; the API authorizes every call again.
import { useMemo } from "react";
import { useAppContext } from "@/components/app-context";
import { peopleIndex } from "@/components/incident/people";
import { PageHeader } from "@/components/layout";
import { DeliveryOutbox } from "@/components/notifications/delivery-outbox";
import { NotificationList } from "@/components/notifications/notification-list";
import { useApi } from "@/lib/hooks";
import { meOrgWideCan } from "@/lib/permissions";
import type { Member } from "@/lib/types";

export default function NotificationsPage() {
  const { me, project } = useAppContext();
  const organizationId = project?.organization_id;
  const showOutbox = meOrgWideCan(me, "VIEW_AUDIT", organizationId);
  const members = useApi<Member[]>(showOutbox && project ? `/projects/${project.id}/members` : null);
  const people = useMemo(() => peopleIndex(members.data), [members.data]);
  const organizationName = me?.memberships.find((m) => m.organization_id === organizationId)?.organization;

  return (
    <>
      <PageHeader
        title="Notifications"
        subtitle="Workflow events that need your attention: critical incidents, reviews, assignments and verifications."
      />
      <div className="space-y-4">
        <NotificationList />
        {showOutbox && organizationId ? (
          <DeliveryOutbox
            organizationId={organizationId}
            organizationName={organizationName}
            canRetry={meOrgWideCan(me, "MANAGE_PROJECTS", organizationId)}
            people={people}
          />
        ) : null}
      </div>
    </>
  );
}
