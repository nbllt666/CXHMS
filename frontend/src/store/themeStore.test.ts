import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useThemeStore } from './themeStore'

describe('themeStore', () => {
  beforeEach(() => {
    useThemeStore.setState({
      theme: 'system',
      sidebarCollapsed: false
    })
    localStorage.clear()
  })

  describe('initial state', () => {
    it('should have system theme by default', () => {
      const state = useThemeStore.getState()
      expect(state.theme).toBe('system')
    })

    it('should have sidebar expanded by default', () => {
      const state = useThemeStore.getState()
      expect(state.sidebarCollapsed).toBe(false)
    })
  })

  describe('setTheme', () => {
    it('should set light theme', () => {
      useThemeStore.getState().setTheme('light')
      expect(useThemeStore.getState().theme).toBe('light')
    })

    it('should set dark theme', () => {
      useThemeStore.getState().setTheme('dark')
      expect(useThemeStore.getState().theme).toBe('dark')
    })

    it('should set system theme', () => {
      useThemeStore.getState().setTheme('dark')
      useThemeStore.getState().setTheme('system')
      expect(useThemeStore.getState().theme).toBe('system')
    })

    it('should persist theme to localStorage', () => {
      const setItemSpy = vi.spyOn(Storage.prototype, 'setItem')
      useThemeStore.getState().setTheme('dark')
      expect(setItemSpy).toHaveBeenCalledWith('cxhms-theme', 'dark')
    })
  })

  describe('toggleSidebar', () => {
    it('should toggle sidebar from expanded to collapsed', () => {
      useThemeStore.getState().toggleSidebar()
      expect(useThemeStore.getState().sidebarCollapsed).toBe(true)
    })

    it('should toggle sidebar from collapsed to expanded', () => {
      useThemeStore.getState().toggleSidebar()
      useThemeStore.getState().toggleSidebar()
      expect(useThemeStore.getState().sidebarCollapsed).toBe(false)
    })

    it('should persist sidebar state to localStorage', () => {
      const setItemSpy = vi.spyOn(Storage.prototype, 'setItem')
      useThemeStore.getState().toggleSidebar()
      expect(setItemSpy).toHaveBeenCalledWith('cxhms-sidebar-collapsed', 'true')
    })
  })

  describe('isDark', () => {
    it('should return true for dark theme', () => {
      useThemeStore.getState().setTheme('dark')
      expect(useThemeStore.getState().isDark()).toBe(true)
    })

    it('should return false for light theme', () => {
      useThemeStore.getState().setTheme('light')
      expect(useThemeStore.getState().isDark()).toBe(false)
    })

    it('should respect system preference for system theme', () => {
      useThemeStore.getState().setTheme('system')
      const mediaQueryList = window.matchMedia('(prefers-color-scheme: dark)')
      expect(useThemeStore.getState().isDark()).toBe(mediaQueryList.matches)
    })
  })
})
