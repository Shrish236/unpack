// React Query hooks for the dashboard pages. Governance decisions return the whole inbox, so each one
// replaces the cached inbox instead of refetching it.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchAnalyses, fetchExec, fetchGovernance, fetchRepoDashboard, fetchRepos, fetchTeam, fetchTeams,
  type GovernanceState, type Period,
} from "./api";

const governanceKey = (repo?: string) => ["governance", repo ?? ""] as const;

export const useExec = (period: Period) =>
  useQuery({ queryKey: ["exec", period], queryFn: () => fetchExec(period), placeholderData: keepPreviousData });
export const useRepos = () => useQuery({ queryKey: ["repos"], queryFn: fetchRepos });
export const useRepoDashboard = (repo: string) =>
  useQuery({ queryKey: ["repo-dashboard", repo], queryFn: () => fetchRepoDashboard(repo), enabled: !!repo, placeholderData: keepPreviousData });
export const useAnalyses = (repo?: string) =>
  useQuery({ queryKey: ["analyses", repo ?? ""], queryFn: () => fetchAnalyses(repo), placeholderData: keepPreviousData });
export const useTeams = () => useQuery({ queryKey: ["teams"], queryFn: fetchTeams });
export const useTeam = (id: string) => useQuery({ queryKey: ["team", id], queryFn: () => fetchTeam(id) });
export const useGovernance = (repo?: string) =>
  useQuery({ queryKey: governanceKey(repo), queryFn: () => fetchGovernance(repo), placeholderData: keepPreviousData });

export function useGovernanceAction<A>(run: (arg: A) => Promise<GovernanceState>, repo?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: (state) => { queryClient.setQueryData(governanceKey(repo), state); },
  });
}
