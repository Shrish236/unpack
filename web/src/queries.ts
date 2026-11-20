// React Query hooks for the dashboard pages. Governance decisions return the whole inbox, so each one
// replaces the cached inbox instead of refetching it.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchExec, fetchGovernance, fetchTeam, fetchTeams, type GovernanceState, type Period } from "./api";

const GOVERNANCE_KEY = ["governance"] as const;

export const useExec = (period: Period) =>
  useQuery({ queryKey: ["exec", period], queryFn: () => fetchExec(period), placeholderData: keepPreviousData });
export const useTeams = () => useQuery({ queryKey: ["teams"], queryFn: fetchTeams });
export const useTeam = (id: string) => useQuery({ queryKey: ["team", id], queryFn: () => fetchTeam(id) });
export const useGovernance = () => useQuery({ queryKey: GOVERNANCE_KEY, queryFn: fetchGovernance });

export function useGovernanceAction<A>(run: (arg: A) => Promise<GovernanceState>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: (state) => { queryClient.setQueryData(GOVERNANCE_KEY, state); },
  });
}
