import { apiClient } from "./client";
import type { AuthUser, MeResponse, TokenPairResponse } from "./types";

export function register(email: string, password: string) {
  return apiClient.post<AuthUser>("/v1/auth/register", { email, password }, { auth: false });
}

export function login(email: string, password: string) {
  return apiClient.post<TokenPairResponse>("/v1/auth/login", { email, password }, { auth: false });
}

export function me() {
  return apiClient.get<MeResponse>("/v1/auth/me");
}
